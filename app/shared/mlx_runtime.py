from __future__ import annotations

import gc


def cleanup_mlx(*, collect_garbage: bool = False) -> None:
    if collect_garbage:
        gc.collect()
    try:
        import mlx.core as mx

        mx.clear_cache()
        mx.clear_streams()
    except Exception:
        pass

