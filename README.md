# openSDC-Bench

**Open Scientific Data Compression Benchmark Suite**

openSDC-Bench 是一个面向科学数据压缩的开放、可扩展评测套件。它在公开的统一评测协议下，比较不同压缩方法在多种科学数据和误差界上的压缩率、吞吐量与重建质量，帮助研究者观察不同方法的表现和权衡。排行榜按数据集、误差界和指标组织可比较的结果，测量记录、数据处理规则和压缩器版本可供核查。

当前结果覆盖 SDRBench 的 NYX、CESM、JHTDB、Hurricane、Miranda 和 SCALE，以及 ZFP、PFPL、SPERR、SZ3 和 Falcons。除 PSNR、NRMSE 和 SSIM 外，套件还提供相关性、自相关和频谱等质量分析。支持注册自定义压缩器与领域指标；具体下游任务评测仍在规划中。

Python 包名 `lfcbenchmark`、导入名和命令 `lfcbench` 继续使用原名称。

压缩器和指标支持 `general`、`domain_specific`、`particle` 等可组合分类。
分类元数据、领域指标注册、排行榜分组和发布规则见
[注册与排行榜说明](docs/leaderboard.md)。

Python 接口支持 CPU 上的 SZ3、ZFP、无压缩对照，以及由用户注册的自定义压缩器。

## Benchmark 结果

[结果网页](https://binglucs.github.io/openSDC-Bench-site/) 收录六组 SDRBench 数据（包括 NYX）和 Python 接口验证。网页提供 RD 曲线、压缩比、吞吐量、`1E-3` 帕累托前沿，以及逐次测量、汇总 CSV 和误差校验结果。单线程原生 API 测试覆盖 ZFP、PFPL、SPERR、SZ3 和 Falcons。

网页的 View 菜单提供压缩率表，以及 PSNR、SSIM、PCC、NRMSE、频谱误差、自相关与变量间相关性变化的码率曲线。SSIM 和 Pearson 图使用原始分数，主图缩短高码率平台段，完整范围可通过 Full rate range 查看。曲线使用 `1E-1` 至 `1E-5` 的误差界，统计方法和重新生成命令见[质量曲线说明](docs/quality-rd.md)。

公开结果、审计和图表位于 [`docs/data/`](docs/data/)，[独立网页仓库](https://github.com/BingluCS/openSDC-Bench-site)维护网站和自动发布流程。网站定期读取本仓库并重新校验、生成排行榜；详见[结果发布说明](docs/publication.md)。[`scripts/export_web_results.py`](scripts/export_web_results.py) 从已校验的测试目录和对应绘图目录生成网页数据。

## 项目结构与社区贡献

| 目录 | 内容 |
| --- | --- |
| [`src/lfcbench/`](src/lfcbench/) | Python 接口、压缩器和质量指标注册 |
| [`native/`](native/)、[`native_typed/`](native_typed/) | 单线程 C++ 原生评测驱动 |
| [`quality/`](quality/) | LFCQuality C/C++ 和 Python 质量分析库 |
| [`datasets/`](datasets/) | 数据来源、字段清单与获取说明 |
| [`scripts/`](scripts/) | 数据验证、实验、审计、绘图和榜单生成 |
| [`tests/`](tests/)、[`examples/`](examples/) | 自动化检查及插件示例 |
| [`third_party/`](third_party/) | 固定版本的上游压缩器源码 |

欢迎社区 fork 并提交 PR。加入新结果需要匹配字段、误差界与计时协议，并提交数据和可审计记录；详见[贡献指南](CONTRIBUTING.md)和[数据集说明](datasets/README.md)。JHTDB 的历史结果保留，其原始数据来源与裁剪过程确认后再提供复现清单。

## 快速开始

克隆仓库并安装 Python 接口与可选的 CPU 压缩器：

```bash
git clone --recurse-submodules https://github.com/BingluCS/openSDC-Bench.git
cd openSDC-Bench
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[cpu,plot,test]'

lfcbench list
lfcbench inspect sz3
lfcbench validate sz3
lfcbench validate zfp

# 先将示例配置中的路径、类型和形状修改为自己的数据。
# 线程环境需要在启动 Python 之前设置。
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  lfcbench run examples/server-data.yaml -o results/my-run.jsonl
lfcbench report results/my-run.jsonl --csv results/my-run.csv
lfcbench plot results/my-run.jsonl --output-dir results/my-plots
```

结果文件采用独占创建，已存在时不会覆盖；下次运行请使用新文件名。`examples/server-data.yaml` 中的路径只用于说明配置格式，运行前请按自己的数据修改，并核对维度和内存顺序。也可以使用已有的 Conda Python 环境。

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
- 保存完整参数、范围、绝对误差上限、Python/NumPy/压缩器版本、主机与线程环境。失败也会保存到 JSONL，非零退出码表示出现失败或超限。
- JSONL 是逐次原始记录；`report` 只用通过检查的重复计算中位数，同时列出失败和超限数。

`plot` 按数据集生成 rate–distortion、压缩和解压吞吐图。零 RMSE 的点不出现在对数误差图中，但仍在吞吐图和原始记录里。

Python 适配器路径当前没有自动续跑、GPU 执行或针对具体科学任务的内建质量指标。大数组的完整载入、复制和误差分析会消耗额外内存；规模化运行前应评估内存需求。正式比较时应固定线程和机器状态，核对字段布局、算法设置和版本。

## SDRBench 原生接口测试

网页使用的五个压缩器通过 `native/` 和 `native_typed/` 下的 C++ 驱动调用原生 API；
这与上面的 Python 压缩器适配器是两条独立的测试路径。`third_party/` 的 Git
submodule 和 `sources.lock.json` 固定了五个官方仓库的版本。首次克隆后，在 Linux
源码目录中执行：

```bash
git submodule update --init --recursive
python -m pip install -e '.[plot,test]'
# 需要 CMake、C++20 编译器、OpenMP 和 Zstd 开发库；构建使用 -march=native。
lfcbench native-build --jobs 4
lfcbench native-build-typed

# 检查本地数据的 dtype、形状和范围，再选择实验参数。
lfcbench native-inventory --data-root /data0/lb/sdrbench --datasets NYX --output results/sdrbench-inventory.json
lfcbench native-suite --inventory results/sdrbench-inventory.json \
  --output results/my-sdrbench --datasets NYX --cpu 2
lfcbench native-suite-audit results/my-sdrbench --check-inputs
lfcbench native-suite-plot results/my-sdrbench --output results/my-sdrbench-plots
```

`native-suite --help` 可选择数据集、误差范围、压缩器和重复次数。驱动使用单线程
原生 API 计时，记录原始结果并单独验证误差；`native/` 为 float32 3D 路径，
`native_typed/` 还支持原始 float64 和真正的 2D 输入。进程启动、文件读取、输入复制
及验证不计入压缩/解压时间。结果记录名义误差和实际传给压缩器的容差；SPERR float32
保留舍入余量，SZ3 的边界重试也保留原始失败记录。具体源版本见 `sources.lock.json`，
参考实验的仓库版本见 `reference.lock.json`。完整数据、审计报告和当时的 Git 源码
快照可从网页下载；源码快照也可在本仓库使用 `git clone docs/data/sdrbench/native-source.bundle <目标目录>` 检出。

## 可注册的质量指标

`lfcbench list-metrics` 列出可选的质量分析插件。它们通过
`lfcbenchmark.metrics` Python entry point 自动发现，也可以直接注册：

```python
from lfcbench import register_metric

@register_metric("my_lab.quality")
def quality(original, reconstructed, **options):
    # 输入是只读 NumPy 视图，返回可用严格 JSON 序列化的 dict。
    return {"custom_score": 1.0}
```

[LFCQuality](quality/) 已作为 `quality/` 中的独立组件纳入本仓库，使用 C++ / OpenMP
数值内核和 FFTW，提供 PSNR、SSIM、PCC、误差自相关、场自相关差异和频谱误差。
在已安装 openSDC-Bench 的同一个 Python 环境中安装并构建：

```bash
# 从当前仓库安装质量分析组件；安装是可选的。
python -m pip install -e ./quality
# 需要 C++17 编译器、OpenMP 和带线程库的 FFTW；依赖安装见 LFCQuality 文档。
lfcquality build --openmp required --fftw required
lfcbench list-metrics
```

HPDPS-8 的 `py3.13` 环境已经安装 LFCQuality；执行 `conda activate py3.13` 后可在
`/data0/lb/lfcbenchmark` 使用。其 FFTW 位于 `/data0/lb/lfcquality/.native-deps`，如需重新编译，先设置
`export LFCQUALITY_FFTW_PREFIX=/data0/lb/lfcquality/.native-deps`。安装后在 YAML 中加入：

```yaml
quality_metrics:
  - name: lfcquality
    options:
      metrics: [psnr, pcc, ssim, error_autocorrelation, autocorrelation, spectral]
      threads: 1
      fft_threads: 1
      ssim_window: 7
      ssim_stride: 4
```

Python API 的 `benchmark(..., quality_metrics=[{"name": "lfcquality", "options": {"threads": 1}}])`
采用同样配置。结果保存在 `metrics.quality.lfcquality`，仅在正式测量中调用，
位于压缩和解压计时之外。默认不运行插件；原有配置保持兼容。分析失败会明确
报错，不生成伪造的分数。每条记录同时保存所请求的插件及参数。多个变量的相关性
变化需向 LFCQuality 的 `analyze_fields` 提供同一网格、同一时刻的多组原始场和重建场。

分析线程不会设置压缩器线程数，但多线程分析仍可能影响后续实验的机器状态；
正式吞吐量实验建议单独运行分析，或在启动进程前配置 `OMP_WAIT_POLICY=PASSIVE`。
现有 SDRBench 原生五压缩器测试使用独立的 C++ 驱动，尚未通过此 Python 插件接口
自动执行 LFCQuality；已发布记录也没有保存重建数组，不能从已有的汇总数值推算新指标。
如需对这些压缩器计算新指标，需要分别保存或重新生成重建数据后运行 LFCQuality。

## 测试

```bash
python -m pytest -q
```
