from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional

class ScriptureLocation(BaseModel):
    """经文定位信息"""
    # 允许模型多返回字段时静默忽略，提升结构化输出鲁棒性
    model_config = ConfigDict(extra="ignore")

    work_id: str = Field(description="经号，如 T0001")
    work_title: str = Field(description="经名")
    juan: str = Field(description="卷号")
    dynasty: Optional[str] = Field(description="朝代")
    author: Optional[str] = Field(description="作译者")
    category: Optional[str] = Field(description="部类")
    canon: Optional[str] = Field(description="藏经，如 T=大正藏")
    source: Optional[str] = Field(
        default=None,
        description="来源：如 'CBETA'、'Gallica' 等"
    )
    external_url: Optional[str] = Field(
        default=None,
        description="该出处对应的在线阅览 URL（如 Gallica/CBETA 在线阅读链接）"
    )
    snippet: str = Field(description="匹配的文本片段")
    match_score: Optional[int] = Field(description="原始匹配分数（如相似度搜索返回的分数）")
    confidence: float = Field(description="置信度 0.0-1.0，根据标准计算")
    confidence_reason: str = Field(description="置信度评估依据")

class OCRResult(BaseModel):
    """OCR 识别结果"""
    model_config = ConfigDict(extra="ignore")

    recognized_text: str = Field(description="识别出的完整文字（繁体中文）")
    uncertain_chars: List[str] = Field(
        default_factory=list,
        description="标记为不确定的字符列表"
    )
    word_segmentation: List[str] = Field(
        default_factory=list,
        description="分词结果"
    )

class FinalAnswer(BaseModel):
    """AI 最终答案"""
    model_config = ConfigDict(extra="ignore")

    ocr_result: OCRResult
    scripture_locations: List[ScriptureLocation] = Field(
        default_factory=list,
        description="按置信度排序的可能经段列表，最多5条"
    )
    ocr_notes: List[str] = Field(
        default_factory=list,
        description="逐列/逐句的 OCR 摘要，含不确定说明"
    )
    candidate_insights: List[str] = Field(
        default_factory=list,
        description="对候选经文的关键洞察与比对提示"
    )
    key_facts: List[str] = Field(
        default_factory=list,
        description="片段关键信息：物质形态、题记/尾题、装帧与残损等，从图像与正文中直接可见的要点"
    )
    verification_points: List[str] = Field(
        default_factory=list,
        description="人工需要校对或复查的要点"
    )
    next_actions: List[str] = Field(
        default_factory=list,
        description="对研究者的后续建议或操作步骤"
    )
    reasoning: str = Field(description="AI 的推理过程和依据")
    search_iterations: int = Field(
        default=0,
        description="执行的搜索次数"
    )
    tools_used: List[str] = Field(
        default_factory=list,
        description="使用的工具列表"
    )
    session_id: Optional[str] = Field(
        default=None,
        description="会话ID，用于多轮对话"
    )
