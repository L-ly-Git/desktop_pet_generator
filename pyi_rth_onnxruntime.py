# -*- coding: utf-8 -*-
# 运行时钩子：在 Qt 之前导入 onnxruntime，避免 DLL 加载顺序冲突导致 access violation。
def _pyi_rthook():
    import onnxruntime  # noqa: F401


_pyi_rthook()
del _pyi_rthook
