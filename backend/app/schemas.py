"""接口出入参模型：列表分页、动作结果与各模块的明细结构。"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageResult(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    size: int = 20


class ActionResult(BaseModel):
    ok: bool
    message: str
    entry: dict[str, Any] | None = None


class EntryPayload(BaseModel):
    """登记或修改一条业务记录时提交的字段集合。"""

    values: dict[str, Any] = Field(default_factory=dict)
    remark: str | None = None


class ActionPayload(BaseModel):
    """状态动作使用独立契约，避免与登记的 values 载荷混用。"""

    action: str
    remark: str | None = None



class SiteProfileEntry(BaseModel):
    """目标站点明细结构。"""

    field_0: str | None = None  # 站点编号
    field_1: str | None = None  # 域名
    field_2: str | None = None  # 编码格式
    field_3: str | None = None  # 反爬等级
    field_4: str | None = None  # 合规说明
    field_5: str | None = None  # 负责人
    field_6: str | None = None  # 接入状态
    field_7: str | None = None  # 最后爬取

class ProxyPoolEntry(BaseModel):
    """代理节点明细结构。"""

    field_0: str | None = None  # 节点编号
    field_1: str | None = None  # 代理类型
    field_2: str | None = None  # IP地址
    field_3: str | None = None  # 端口号
    field_4: str | None = None  # 匿名等级
    field_5: str | None = None  # 响应延迟
    field_6: str | None = None  # 成功率
    field_7: str | None = None  # 最后检测

class CookieVaultEntry(BaseModel):
    """会话凭证明细结构。"""

    field_0: str | None = None  # 凭证编号
    field_1: str | None = None  # 关联站点
    field_2: str | None = None  # Cookie文本
    field_3: str | None = None  # UserAgent
    field_4: str | None = None  # 过期时间
    field_5: str | None = None  # 刷新策略
    field_6: str | None = None  # 最后验证
    field_7: str | None = None  # 登录方式

class RateLimiterEntry(BaseModel):
    """请求策略明细结构。"""

    field_0: str | None = None  # 策略编号
    field_1: str | None = None  # 目标站点
    field_2: str | None = None  # 每秒上限
    field_3: str | None = None  # 并发连接
    field_4: str | None = None  # 退避系数
    field_5: str | None = None  # 最大重试
    field_6: str | None = None  # 窗口粒度
    field_7: str | None = None  # 生效时段

class ExtractRuleEntry(BaseModel):
    """抽取规则明细结构。"""

    field_0: str | None = None  # 规则编号
    field_1: str | None = None  # 目标站点
    field_2: str | None = None  # 页面类型
    field_3: str | None = None  # 字段路径
    field_4: str | None = None  # 提取方式
    field_5: str | None = None  # 缺省值
    field_6: str | None = None  # 校验正则
    field_7: str | None = None  # 规则优先级

class CrawlTaskEntry(BaseModel):
    """任务批次明细结构。"""

    field_0: str | None = None  # 任务编号
    field_1: str | None = None  # 目标站点
    field_2: str | None = None  # 入口URL
    field_3: str | None = None  # 深度限制
    field_4: str | None = None  # 页面上限
    field_5: str | None = None  # 调度cron
    field_6: str | None = None  # 优先级
    field_7: str | None = None  # 截止时间

class RpaScriptEntry(BaseModel):
    """自动化脚本明细结构。"""

    field_0: str | None = None  # 脚本编号
    field_1: str | None = None  # 目标应用
    field_2: str | None = None  # 触发事件
    field_3: str | None = None  # 操作序列
    field_4: str | None = None  # 超时秒数
    field_5: str | None = None  # 等待条件
    field_6: str | None = None  # 错误处理
    field_7: str | None = None  # 脚本版本

class DataPipelineEntry(BaseModel):
    """流水线段明细结构。"""

    field_0: str | None = None  # 段编号
    field_1: str | None = None  # 输入来源
    field_2: str | None = None  # 转换算子
    field_3: str | None = None  # 输出目标
    field_4: str | None = None  # 依赖段
    field_5: str | None = None  # 并行度
    field_6: str | None = None  # 失败策略
    field_7: str | None = None  # 超时分钟

class ResultStoreEntry(BaseModel):
    """结果批次明细结构。"""

    field_0: str | None = None  # 批次编号
    field_1: str | None = None  # 关联任务
    field_2: str | None = None  # 原始行数
    field_3: str | None = None  # 有效行数
    field_4: str | None = None  # 存储路径
    field_5: str | None = None  # 压缩格式
    field_6: str | None = None  # 校验摘要
    field_7: str | None = None  # 落地时间

class AntiBlockEntry(BaseModel):
    """对抗策略明细结构。"""

    field_0: str | None = None  # 策略编号
    field_1: str | None = None  # 目标站点
    field_2: str | None = None  # 触发特征
    field_3: str | None = None  # 应对动作
    field_4: str | None = None  # 切换耗时
    field_5: str | None = None  # 成功率
    field_6: str | None = None  # 生效时段
    field_7: str | None = None  # 备注

class QualityCheckEntry(BaseModel):
    """审计记录明细结构。"""

    field_0: str | None = None  # 记录编号
    field_1: str | None = None  # 关联批次
    field_2: str | None = None  # 检查项
    field_3: str | None = None  # 阈值
    field_4: str | None = None  # 实际值
    field_5: str | None = None  # 判定结果
    field_6: str | None = None  # 审计时间
    field_7: str | None = None  # 处理建议

class DeltaSyncEntry(BaseModel):
    """同步水位明细结构。"""

    field_0: str | None = None  # 水位编号
    field_1: str | None = None  # 源数据集
    field_2: str | None = None  # 增量字段
    field_3: str | None = None  # 上次水位
    field_4: str | None = None  # 当前水位
    field_5: str | None = None  # 同步周期
    field_6: str | None = None  # 捕获行数
    field_7: str | None = None  # 最后同步

class LogMonitorEntry(BaseModel):
    """监控事件明细结构。"""

    field_0: str | None = None  # 事件编号
    field_1: str | None = None  # 事件类型
    field_2: str | None = None  # 严重级别
    field_3: str | None = None  # 关联任务
    field_4: str | None = None  # 事件摘要
    field_5: str | None = None  # 触发时间
    field_6: str | None = None  # 恢复状态
    field_7: str | None = None  # 处理人

class TemplateMgrEntry(BaseModel):
    """采集模板明细结构。"""

    field_0: str | None = None  # 模板编号
    field_1: str | None = None  # 适用站点
    field_2: str | None = None  # 模板类型
    field_3: str | None = None  # 版本号
    field_4: str | None = None  # 下载次数
    field_5: str | None = None  # 评分
    field_6: str | None = None  # 兼容说明
    field_7: str | None = None  # 发布者

class ExportHubEntry(BaseModel):
    """分发通道明细结构。"""

    field_0: str | None = None  # 通道编号
    field_1: str | None = None  # 输出格式
    field_2: str | None = None  # 目标地址
    field_3: str | None = None  # 加密方式
    field_4: str | None = None  # 压缩选项
    field_5: str | None = None  # 分片大小
    field_6: str | None = None  # 重试上限
    field_7: str | None = None  # 回调地址

class SchedulerEntry(BaseModel):
    """调度计划明细结构。"""

    field_0: str | None = None  # 计划编号
    field_1: str | None = None  # 关联任务
    field_2: str | None = None  # Cron表达式
    field_3: str | None = None  # 时区
    field_4: str | None = None  # 重试次数
    field_5: str | None = None  # 失败通知
    field_6: str | None = None  # 并发上限
    field_7: str | None = None  # 下次执行

class ParseEngineEntry(BaseModel):
    """解析配置明细结构。"""

    field_0: str | None = None  # 配置编号
    field_1: str | None = None  # 页面类型
    field_2: str | None = None  # 引擎类型
    field_3: str | None = None  # 解析规则
    field_4: str | None = None  # 字符编码
    field_5: str | None = None  # 容错模式
    field_6: str | None = None  # 输出Schema
    field_7: str | None = None  # 版本号

class RetryQueueEntry(BaseModel):
    """重试条目明细结构。"""

    field_0: str | None = None  # 条目编号
    field_1: str | None = None  # 失败页面
    field_2: str | None = None  # 失败原因
    field_3: str | None = None  # 重试次数
    field_4: str | None = None  # 最大重试
    field_5: str | None = None  # 下次重试
    field_6: str | None = None  # 错误详情
    field_7: str | None = None  # 关联任务
