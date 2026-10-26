from __future__ import annotations

import datetime as dt
import io
import time
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np

CACHE = Path(__file__).resolve().parent.parent / ".cache"


def utc(milliseconds: float) -> str:
    """ISO 8601 UTC from an Earth Engine timestamp."""
    when = dt.datetime.fromtimestamp(milliseconds / 1000, dt.UTC)
    return when.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def ee_init():
    import ee

    ee.Initialize()
    return ee


def ee_pixels(expression, bands: list[str], crs: str, transform, shape) -> np.ndarray:
    """Read a window of an Earth Engine image on its delivered grid."""
    import ee

    x0, dx, _, y0, _, dy = transform
    grid = {
        "dimensions": {"width": shape[1], "height": shape[0]},
        "affineTransform": {
            "scaleX": dx,
            "shearX": 0,
            "translateX": x0,
            "shearY": 0,
            "scaleY": dy,
            "translateY": y0,
        },
    }
    grid["crsWkt" if crs.startswith(("PROJCS", "GEOGCS", "PROJCRS")) else "crsCode"] = (
        crs
    )
    for attempt in range(5):
        try:
            record = ee.data.computePixels(
                {
                    "expression": expression,
                    "fileFormat": "NUMPY_NDARRAY",
                    "bandIds": bands,
                    "grid": grid,
                }
            )
            return np.stack([np.ascontiguousarray(record[band]) for band in bands])
        except ee.EEException as error:
            if (
                "Too Many Requests" not in str(error)
                and "deadline" not in str(error).lower()
            ):
                raise
            time.sleep(2**attempt)
    raise RuntimeError("Earth Engine kept refusing the request")


def cog_window(url: str, transform, shape, bands=None) -> tuple[np.ndarray, str]:
    """Read a north-up window of a GeoTIFF on its own grid."""
    import rasterio
    from rasterio.windows import Window

    x0, dx, _, y0, _, dy = transform
    rows, cols = shape
    with rasterio.open(url) as src:
        t = src.transform
        if (
            t.b
            or t.d
            or abs(t.a - dx) > 1e-9 * abs(dx)
            or abs(abs(t.e) - abs(dy)) > 1e-9 * abs(dy)
        ):
            raise ValueError(f"{url} is not on the grid of the window")
        col = (x0 - t.c) / t.a
        row = (t.f - y0) / -t.e if t.e < 0 else (y0 + rows * dy - t.f) / t.e
        if abs(col - round(col)) > 1e-6 or abs(row - round(row)) > 1e-6:
            raise ValueError(f"the window is not aligned to the grid of {url}")
        col, row = round(col), round(row)
        if col < 0 or row < 0 or col + cols > src.width or row + rows > src.height:
            raise ValueError(f"the window leaves {url}")
        data = src.read(indexes=bands, window=Window(col, row, cols, rows))
        crs = src.crs.to_string()
    if t.e > 0:
        data = data[..., ::-1, :]
    return np.ascontiguousarray(data), crs


def http_range(url: str, start: int, end: int, attempts: int = 5) -> bytes:
    headers = {
        "Range": f"bytes={start}-{end}",
        "Accept-Encoding": "identity",
        "User-Agent": "EarthCompress/0.1",
    }
    error: Exception | None = None
    for attempt in range(attempts):
        try:
            with urlopen(Request(url, headers=headers), timeout=300) as response:
                data = response.read()
            if len(data) != end - start + 1:
                raise OSError(f"short read from {url}")
            return data
        except OSError as caught:
            error = caught
            time.sleep(2**attempt)
    raise OSError(f"could not read {url}: {error}")


def npy_window(url: str, row: int, col: int, rows: int, cols: int) -> np.ndarray:
    """Read rows and columns of a remote C-order ``.npy`` with byte ranges."""
    head = io.BytesIO(http_range(url, 0, 4095))
    version = np.lib.format.read_magic(head)
    shape, fortran, dtype = (
        np.lib.format.read_array_header_1_0(head)
        if version == (1, 0)
        else np.lib.format.read_array_header_2_0(head)
    )
    offset = head.tell()
    inner = int(np.prod(shape[2:], dtype=np.int64)) if len(shape) > 2 else 1
    line = shape[1] * inner * dtype.itemsize
    first = offset + row * line
    raw = http_range(url, first, first + rows * line - 1)
    block = np.frombuffer(raw, dtype=dtype).reshape((rows, shape[1]) + tuple(shape[2:]))
    return np.ascontiguousarray(block[:, col : col + cols])


def era5_grib(day: str) -> Path:
    """One day of the five ERA5 single-level fields as GRIB, cached."""
    path = CACHE / "era5" / f"{day}.grib"
    if path.exists():
        return path
    import cdsapi

    path.parent.mkdir(parents=True, exist_ok=True)
    year, month, dd = day.split("-")
    partial = path.with_suffix(".part")
    cdsapi.Client(quiet=True).retrieve(
        "reanalysis-era5-single-levels",
        {
            "product_type": ["reanalysis"],
            "variable": [
                "mean_sea_level_pressure",
                "2m_temperature",
                "total_cloud_cover",
                "total_precipitation",
                "10m_u_component_of_wind",
            ],
            "year": [year],
            "month": [month],
            "day": [dd],
            "time": [f"{h:02d}:00" for h in range(24)],
            "data_format": "grib",
            "download_format": "unarchived",
        },
        str(partial),
    )
    partial.rename(path)
    return path


def grib_fields(path: Path, short_name: str) -> list[dict]:
    """Packed codes and packing parameters of every message of one field."""
    import eccodes as ec

    fields = []
    with path.open("rb") as stream:
        while (handle := ec.codes_grib_new_from_file(stream)) is not None:
            try:
                if ec.codes_get(handle, "shortName") != short_name:
                    continue
                if ec.codes_get(handle, "packingType") != "grid_simple":
                    raise ValueError(f"{short_name} is not simple packing")
                ref = ec.codes_get_double(handle, "referenceValue")
                e = ec.codes_get(handle, "binaryScaleFactor")
                d = ec.codes_get(handle, "decimalScaleFactor")
                values = ec.codes_get_double_array(handle, "values")
                grid = (ec.codes_get(handle, "Nj"), ec.codes_get(handle, "Ni"))
                scale = 2.0**e * 10.0 ** (-d)
                offset = ref * 10.0 ** (-d)
                codes = np.round((values - offset) / scale)
                if not np.array_equal(codes * scale + offset, values):
                    raise ValueError(f"{short_name}: codes do not reproduce the values")
                fields.append(
                    dict(
                        date=ec.codes_get(handle, "validityDate"),
                        time=ec.codes_get(handle, "validityTime"),
                        shape=grid,
                        lon0=ec.codes_get_double(
                            handle, "longitudeOfFirstGridPointInDegrees"
                        ),
                        lat0=ec.codes_get_double(
                            handle, "latitudeOfFirstGridPointInDegrees"
                        ),
                        dlon=ec.codes_get_double(
                            handle, "iDirectionIncrementInDegrees"
                        ),
                        dlat=ec.codes_get_double(
                            handle, "jDirectionIncrementInDegrees"
                        ),
                        bits=ec.codes_get(handle, "bitsPerValue"),
                        scale=scale,
                        offset=offset,
                        codes=codes.reshape(grid),
                        values=values.astype(np.float32).reshape(grid),
                    )
                )
            finally:
                ec.codes_release(handle)
    fields.sort(key=lambda f: (f["date"], f["time"]))
    return fields


def ee_row(row: dict[str, str], expression=None) -> np.ndarray:
    """Read the sample a manifest row describes from Earth Engine."""
    import ee

    from .build import parse_shape, parse_transform, split

    bands = split(row["bands"])
    shape = parse_shape(row["shape"])
    image = (
        expression if expression is not None else ee.Image(row["asset"]).select(bands)
    )
    data = ee_pixels(
        image, bands, row["crs"], parse_transform(row["transform"]), shape[-2:]
    )
    return data.reshape(shape) if len(shape) == 2 else data


def ee_snap(image, x: float, y: float) -> tuple[str, float, float, float]:
    """Move a window corner onto the native grid of a single-band image."""
    info = image.projection().getInfo()
    a, _, c, _, e, f = info["transform"]
    col = round((x - c) / a)
    row = round((y - f) / e)
    return info["crs"], a, c + col * a, f + row * e


def ee_centre(
    image, lon: float, lat: float, size: int
) -> tuple[str, float, float, float]:
    """Corner of a ``size`` window centred on a point, on the native grid of ``image``."""
    import ee

    info = image.projection().getInfo()
    a, _, c, _, e, f = info["transform"]
    point = ee.Geometry.Point([lon, lat]).transform(ee.Projection(info["crs"]), 0.001)
    x, y = point.coordinates().getInfo()
    col = int((x - c) // a) - size // 2
    row = int((y - f) // e) - size // 2
    return info["crs"], a, c + col * a, f + row * e


def cog_centre(
    url: str, lon: float, lat: float, size: int
) -> tuple[str, tuple[float, ...]]:
    """CRS and GDAL transform of a ``size`` window centred on a point of a GeoTIFF."""
    import rasterio
    from rasterio.windows import Window

    with rasterio.open(url) as src:
        col, row = ~src.transform * (lon, lat)
        window = Window(int(col) - size // 2, int(row) - size // 2, size, size)
        if (
            window.col_off < 0
            or window.row_off < 0
            or window.col_off + size > src.width
            or window.row_off + size > src.height
        ):
            raise ValueError(f"the window at {lon},{lat} leaves {url}")
        t = src.window_transform(window)
        return src.crs.to_string(), (t.c, t.a, t.b, t.f, t.d, t.e)
