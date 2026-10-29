"""Small helpers shared by the pipeline steps."""
import os


def save_parquet(gdf, path):
    """Write via a temporary file and swap it in, so a failed write never deletes the existing file.
    On Windows the swap fails while another process (e.g. an older running app) holds the file open."""
    tmp = path.with_name(path.name + ".tmp")
    gdf.to_parquet(tmp)
    try:
        os.replace(tmp, path)
    except PermissionError as err:
        tmp.unlink(missing_ok=True)
        raise SystemExit(f"{path.name} is locked by another program (stop the Streamlit app and rerun): {err}")
