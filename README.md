# LFCBenchmark

面向科学计算浮点数组的可扩展、有误差验证的压缩 benchmark。首版支持 CPU 上的 SZ3、ZFP、无压缩对照，以及由用户注册的自定义压缩器。

## 快速开始

在本服务器的项目目录执行：

```bash
cd /data/lb/LFCBenchmark
conda activate py3.13

lfcbench list
lfcbench inspect sz3
lfcbench validate sz3
lfcbench validate zfp

# 线程环境需要在启动 Python 之前设置。实际使用的线程数仍应结合压缩器版本确认。
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  lfcbench run examples/server-data.yaml -o results/my-run.jsonl
lfcbench report results/my-run.jsonl --csv results/my-run.csv
lfcbench plot results/my-run.jsonl --output-dir results/my-plots
```

结果文件采用独占创建，已存在时不会覆盖；下次运行请使用新文件名。`examples/server-data.yaml` 引用本机 `/data/lb/crop` 中的三个实际字段，文件大小和 dtype 已检查。**shape `[100, 100, 60]` 暂按文件名推定；正式报告前请对照数据生产过程确认原始维度和内存顺序。**

项目已安装到这台服务器的 `py3.13` Conda 环境中。在另一台机器上，可自行创建环境并安装 CPU 后端：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[cpu,plot,test]'
```

`pysz` 是 SZ3 绑定，`zfpy` 是 ZFP 绑定；绘图功能需要 matplotlib，它们以可选依赖方式安装。`requirements-tested.txt` 记录本机验证时的直接依赖版本，不是完整的跨平台锁文件；重建时仍需考虑其他依赖、平台和 Python 版本。

## 配置

配置文件为 YAML，见 `examples/server-data.yaml`。每个 raw 文件必须明确提供 dtype 和 C-order shape，程序会校验文件长度；也支持 `.npy` 文件。相对路径以配置文件所在目录为基准。

误差模式：

- `abs`：使用指定的最大绝对误差。
- `range_relative`：先算 `epsilon = value * (max - min)`，再给压缩器传入绝对误差；这不是逐元素相对误差。常数场请使用 `abs`。

框架当前接受有限的 float32/float64、CPU、1D/2D/3D C-order 数组。NaN、Inf、非本机字节序和零长度数组会明确报错；GPU 和其他误差语义尚未实现。

## 自定义压缩器：本地注册

参考 `examples/local_plugin.py`。在可导入模块中使用：

```python
from lfcbench import register_compressor
from lfcbench.compressors import IdentityCompressor

@register_compressor("my_lab.copy")
class MyCodec(IdentityCompressor):
    pass
```

这是最小注册示例；实际压缩器应继承 `lfcbench.Compressor`，实现 `capabilities`、`compress`、`decompress`。在项目根目录可以运行：

```bash
lfcbench --plugin examples.local_plugin list
lfcbench --plugin examples.local_plugin validate local.identity
```

`--plugin` 可重复指定。模块在构造 registry 之前导入，因此命令行和 Python 进程都能使用它注册的类；用户需要将模块放在 Python 可导入的路径上。

也可以通过 Python API 测试单个数组（完整记录和重复测量使用 YAML 命令行）：

```python
import numpy as np
from lfcbench import AbsoluteError, benchmark, register_compressor
from lfcbench.compressors import IdentityCompressor

register_compressor("my_lab.copy", IdentityCompressor)
data = np.linspace(0, 1, 512, dtype=np.float32).reshape(8, 8, 8)
result = benchmark(data, compressor="my_lab.copy", error=AbsoluteError(1e-4))
print(result["status"], result["metrics"])
```

## 自定义压缩器：独立插件包

`examples/zlib_plugin/` 是完整的可安装示例。它用 Python 标准库 zlib 实现无损压缩，演示协议及入口点，而不是新增有损算法。

```bash
python -m pip install -e examples/zlib_plugin
lfcbench list
lfcbench inspect example.zlib
lfcbench validate example.zlib

# 同时运行独立插件和本地注册插件：
lfcbench --plugin examples.local_plugin run examples/custom-plugin.yaml -o results/plugin-run.jsonl
```

第三方包的 `pyproject.toml` 使用：

```toml
[project.entry-points."lfcbenchmark.compressors"]
"my_lab.mycodec" = "my_codec.adapter:MyCompressor"
```

入口点指向无参数工厂或 `Compressor` 子类。发现只读取包元数据，使用某一插件时才加载。自定义代码可以包装 Python 库、C/C++ 扩展或外部可执行文件；接入者须清楚说明数据拷贝和进程启动是否在其适配器调用内。**外部可执行文件的启动和 I/O 会被算入适配器调用时间，不能直接与进程内 API 的核心计算时间等同。**

接口：

```python
from lfcbench import Compressor, Capabilities, CompressedData

class MyCompressor(Compressor):
    api_version = 1

    def capabilities(self):
        return Capabilities(dtypes=("float32", "float64"), dimensions=(1, 2, 3))

    def compress(self, array, *, error, options):
        # error.value 是框架计算出的最大绝对误差；按算法实现编码。
        payload = my_encode(array, error.value, options)
        return CompressedData(payload=payload, metadata={"shape": list(array.shape), "dtype": array.dtype.str})

    def decompress(self, artifact):
        # 不可依赖原数组或之前的编码器实例。
        return my_decode(artifact.payload, artifact.metadata)
```

`payload` 必须为 `bytes`，`metadata` 必须可用标准 JSON 序列化，且应包含独立解压必需的信息。无参数工厂每次创建新实例；同名注册报错；框架检查 API 版本与能力声明。插件可以实现 `version_info()` 返回可 JSON 序列化的版本信息。

## 计量和正确性

- 每个组合先预热，再独立记录每次重复；同一数据集内的组合按 seed 洗牌。
- 输入加载、复制、序列化及质量验证不包含在压缩/解压计时中；计时包含 Python 适配器调用。CPU 同步方法为空，GPU 适配和独立 kernel 计时暂不支持。
- 测量压缩后大小时包含框架头部及插件元数据；`payload_bytes` 同时单独记录。吞吐定义为原始字节数除以时间，单位 MiB/s。
- 每次都用新的压缩器实例解压，以 float64 计算最大绝对误差、RMSE、偏差、PSNR、超限点数。`psnr_db: null` 表示零误差或数据范围为零；超限记录不会算作成功。
- 保存完整参数、范围、绝对误差上限、数组 SHA-256、Python/NumPy/压缩器版本、主机与线程环境。失败也会保存到 JSONL，非零退出码表示出现失败或超限。
- JSONL 是逐次原始记录；`report` 只用通过检查的重复计算中位数，同时列出失败和超限数。

`plot` 按数据集生成 rate–distortion、压缩和解压吞吐图。零 RMSE 的点不出现在对数误差图中，但仍在吞吐图和原始记录里。

当前没有自动续跑、GPU 执行或应用领域质量指标。大数组的完整载入、复制和误差分析会消耗额外内存；规模化运行前应评估内存需求。正式比较时应固定线程和机器状态，核对字段布局、算法设置和版本。

## 测试

```bash
python -m pytest -q
```
