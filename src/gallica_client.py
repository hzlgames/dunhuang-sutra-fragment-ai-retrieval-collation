"""
Gallica API 客户端
封装 BnF (法国国家图书馆) 的 SRU 搜索 与 IIIF 图像/Manifest 接口，
用于查找敦煌文献等藏品，与 CBETA 结果进行比对分析。
"""
import time
import requests
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict


@dataclass
class GallicaRecord:
    """Gallica 搜索结果记录"""
    ark: str  # ARK 标识符，如 ark:/12148/btv1b8304226d
    title: str
    date: Optional[str] = None
    creator: Optional[str] = None
    language: Optional[str] = None
    doc_type: Optional[str] = None  # manuscrit, image, etc.
    description: Optional[str] = None
    source: Optional[str] = None
    thumbnail_url: Optional[str] = None
    manifest_url: Optional[str] = None
    gallica_url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class GallicaPageInfo:
    """Gallica 单页信息"""
    ark: str
    page_id: str  # f1, f2, ...
    page_number: int
    width: Optional[int] = None
    height: Optional[int] = None
    image_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    alto_url: Optional[str] = None  # OCR 文本 (ALTO XML)
    annotations_url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class GallicaClient:
    """
    Gallica API 客户端
    
    功能：
    1. SRU 搜索：按关键词搜索敦煌/佛典文献
    2. IIIF Manifest 解析：获取文档结构、页面列表
    3. IIIF 图像 URL 构造：支持裁剪、缩放、格式转换
    4. 节流控制：避免被 BnF 服务器封禁
    """
    
    SRU_BASE = "https://gallica.bnf.fr/SRU"
    IIIF_BASE = "https://gallica.bnf.fr/iiif"
    GALLICA_BASE = "https://gallica.bnf.fr"
    
    # Dublin Core 命名空间
    NS = {
        "srw": "http://www.loc.gov/zing/srw/",
        "dc": "http://purl.org/dc/elements/1.1/",
        "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/"
    }
    
    def __init__(self, request_interval: float = 1.5, timeout: int = 30):
        """
        初始化客户端
        Args:
            request_interval: 请求间隔秒数（避免被封禁）
            timeout: 请求超时秒数
        """
        self.request_interval = request_interval
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "CBETA-Gallica-Research-Tool/1.0"
        })
        self._last_request_time = 0
    
    def _throttle(self):
        """节流控制"""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.request_interval:
            time.sleep(self.request_interval - elapsed)
        self._last_request_time = time.time()
    
    def _get(self, url: str, params: Dict = None) -> requests.Response:
        """带节流的 GET 请求"""
        self._throttle()
        return self.session.get(url, params=params, timeout=self.timeout)
    
    # ========== SRU 搜索 ==========
    
    def search(
        self,
        query: str,
        max_records: int = 10,
        start_record: int = 1,
        doc_type: str = None,
        language: str = None
    ) -> Dict[str, Any]:
        """
        SRU 搜索 Gallica 馆藏
        
        Args:
            query: 搜索关键词（如 "Dunhuang"、"敦煌"、"佛经"）
            max_records: 最大返回数量
            start_record: 起始记录位置
            doc_type: 限制文档类型（manuscrit=手稿, image=图像）
            language: 限制语言（chi=中文, san=梵文）
        
        Returns:
            {
                "status": "success" | "error",
                "total_records": int,
                "records": List[GallicaRecord],
                "message": str (仅在 error 时)
            }
        
        CQL 语法示例：
            - gallica any "Dunhuang" : 全文搜索
            - dc.title all "经" : 标题搜索
            - dc.type adj "manuscrit" : 手稿类型
            - dc.language adj "chi" : 中文
        """
        # 构建 CQL 查询
        cql_parts = [f'gallica any "{query}"']
        if doc_type:
            cql_parts.append(f'dc.type adj "{doc_type}"')
        if language:
            cql_parts.append(f'dc.language adj "{language}"')
        
        cql_query = " and ".join(cql_parts)
        
        params = {
            "operation": "searchRetrieve",
            "version": "1.2",
            "query": cql_query,
            "maximumRecords": max_records,
            "startRecord": start_record
        }
        
        try:
            response = self._get(self.SRU_BASE, params=params)
            if response.status_code == 503:
                return {
                    "status": "error",
                    "message": "Gallica 服务暂时不可用 (503)，请稍后重试",
                    "total_records": 0,
                    "records": []
                }
            response.raise_for_status()
            
            # 检查是否返回 XML
            content_type = response.headers.get("Content-Type", "")
            if "xml" not in content_type.lower():
                return {
                    "status": "error",
                    "message": f"Gallica 返回非 XML 响应: {content_type}",
                    "total_records": 0,
                    "records": []
                }
            
            return self._parse_sru_response(response.text)
        except requests.exceptions.Timeout:
            return {"status": "error", "message": "Gallica 请求超时", "total_records": 0, "records": []}
        except requests.exceptions.ConnectionError:
            return {"status": "error", "message": "无法连接到 Gallica 服务器", "total_records": 0, "records": []}
        except Exception as e:
            return {"status": "error", "message": str(e), "total_records": 0, "records": []}
    
    def search_dunhuang(
        self,
        keyword: str = "",
        max_records: int = 10
    ) -> Dict[str, Any]:
        """
        专门搜索敦煌相关文献
        
        Args:
            keyword: 额外关键词（可选）
            max_records: 最大返回数量
        """
        # 敦煌相关的常用搜索词
        base_query = "Dunhuang OR Touen-houang OR Pelliot OR 敦煌"
        if keyword:
            base_query = f"({base_query}) AND ({keyword})"
        
        return self.search(base_query, max_records=max_records, doc_type="manuscrit")
    
    def _parse_sru_response(self, xml_text: str) -> Dict[str, Any]:
        """解析 SRU XML 响应"""
        try:
            root = ET.fromstring(xml_text)
            
            # 获取总记录数
            num_records_elem = root.find(".//srw:numberOfRecords", self.NS)
            total_records = int(num_records_elem.text) if num_records_elem is not None else 0
            
            records = []
            for record_elem in root.findall(".//srw:record", self.NS):
                dc_elem = record_elem.find(".//oai_dc:dc", self.NS)
                if dc_elem is None:
                    continue
                
                record = self._parse_dc_record(dc_elem)
                if record:
                    records.append(record)
            
            return {
                "status": "success",
                "total_records": total_records,
                "records": [r.to_dict() for r in records]
            }
        except ET.ParseError as e:
            return {"status": "error", "message": f"XML 解析失败: {e}", "total_records": 0, "records": []}
    
    def _parse_dc_record(self, dc_elem: ET.Element) -> Optional[GallicaRecord]:
        """解析 Dublin Core 记录"""
        def get_text(tag: str) -> Optional[str]:
            elem = dc_elem.find(f"dc:{tag}", self.NS)
            return elem.text.strip() if elem is not None and elem.text else None
        
        def get_all_text(tag: str) -> List[str]:
            return [e.text.strip() for e in dc_elem.findall(f"dc:{tag}", self.NS) if e.text]
        
        # 提取 ARK ID
        identifiers = get_all_text("identifier")
        ark = None
        gallica_url = None
        for ident in identifiers:
            if "ark:/12148/" in ident:
                if ident.startswith("http"):
                    gallica_url = ident
                    # 从 URL 提取 ARK
                    ark = "ark:/12148/" + ident.split("ark:/12148/")[1].split("/")[0]
                else:
                    ark = ident
                break
        
        if not ark:
            return None
        
        # 提取 ARK 的短 ID（用于构造 URL）
        ark_id = ark.split("/")[-1]
        
        return GallicaRecord(
            ark=ark,
            title=get_text("title") or "未知标题",
            date=get_text("date"),
            creator=get_text("creator"),
            language=get_text("language"),
            doc_type=get_text("type"),
            description=get_text("description"),
            source=get_text("source"),
            thumbnail_url=f"{self.GALLICA_BASE}/ark:/12148/{ark_id}/thumbnail",
            manifest_url=f"{self.IIIF_BASE}/ark:/12148/{ark_id}/manifest.json",
            gallica_url=gallica_url or f"{self.GALLICA_BASE}/ark:/12148/{ark_id}"
        )
    
    # ========== IIIF Manifest ==========
    
    def get_manifest(self, ark: str) -> Dict[str, Any]:
        """
        获取 IIIF Manifest（文档结构）
        
        Args:
            ark: ARK 标识符或短 ID（如 "btv1b8304226d"）
        
        Returns:
            {
                "status": "success" | "error",
                "ark": str,
                "title": str,
                "total_pages": int,
                "pages": List[GallicaPageInfo],
                "metadata": Dict,
                "raw_manifest": Dict (完整原始 JSON)
            }
        """
        ark_id = self._extract_ark_id(ark)
        manifest_url = f"{self.IIIF_BASE}/ark:/12148/{ark_id}/manifest.json"
        
        try:
            response = self._get(manifest_url)
            response.raise_for_status()
            manifest = response.json()
            return self._parse_manifest(ark_id, manifest)
        except Exception as e:
            return {"status": "error", "message": str(e), "ark": ark_id}
    
    def _parse_manifest(self, ark_id: str, manifest: Dict) -> Dict[str, Any]:
        """解析 IIIF Manifest"""
        title = manifest.get("label", "未知标题")
        if isinstance(title, dict):
            title = title.get("@value", str(title))
        
        # 提取元数据
        metadata = {}
        for item in manifest.get("metadata", []):
            label = item.get("label", "")
            value = item.get("value", "")
            if isinstance(label, dict):
                label = label.get("@value", str(label))
            if isinstance(value, dict):
                value = value.get("@value", str(value))
            metadata[label] = value
        
        # 解析页面
        pages = []
        sequences = manifest.get("sequences", [])
        if sequences:
            canvases = sequences[0].get("canvases", [])
            for idx, canvas in enumerate(canvases):
                page_info = self._parse_canvas(ark_id, idx + 1, canvas)
                if page_info:
                    pages.append(page_info.to_dict())
        
        return {
            "status": "success",
            "ark": ark_id,
            "title": title,
            "total_pages": len(pages),
            "pages": pages,
            "metadata": metadata,
            "manifest_url": f"{self.IIIF_BASE}/ark:/12148/{ark_id}/manifest.json"
        }
    
    def _parse_canvas(self, ark_id: str, page_num: int, canvas: Dict) -> Optional[GallicaPageInfo]:
        """解析单个 Canvas（页面）"""
        canvas_id = canvas.get("@id", "")
        page_id = f"f{page_num}"
        
        # 从 canvas ID 中提取页码（如有）
        if "/f" in canvas_id:
            page_id = "f" + canvas_id.split("/f")[-1].split("/")[0]
        
        width = canvas.get("width")
        height = canvas.get("height")
        
        # 图像信息
        image_url = None
        images = canvas.get("images", [])
        if images:
            resource = images[0].get("resource", {})
            service = resource.get("service", {})
            service_id = service.get("@id", "")
            if service_id:
                image_url = f"{service_id}/full/full/0/native.jpg"
        
        # ALTO OCR（通常在 seeAlso 或 otherContent 中）
        alto_url = None
        see_also = canvas.get("seeAlso", [])
        if isinstance(see_also, list):
            for item in see_also:
                if isinstance(item, dict) and "alto" in item.get("format", "").lower():
                    alto_url = item.get("@id")
                    break
        
        # 注释（otherContent）
        annotations_url = None
        other_content = canvas.get("otherContent", [])
        if isinstance(other_content, list) and other_content:
            if isinstance(other_content[0], dict):
                annotations_url = other_content[0].get("@id")
            elif isinstance(other_content[0], str):
                annotations_url = other_content[0]
        
        return GallicaPageInfo(
            ark=ark_id,
            page_id=page_id,
            page_number=page_num,
            width=width,
            height=height,
            image_url=image_url,
            thumbnail_url=f"{self.IIIF_BASE}/ark:/12148/{ark_id}/{page_id}/full/,150/0/native.jpg",
            alto_url=alto_url,
            annotations_url=annotations_url
        )
    
    # ========== IIIF 图像 URL 构造 ==========
    
    def build_image_url(
        self,
        ark: str,
        page: str = "f1",
        region: str = "full",
        size: str = "full",
        rotation: int = 0,
        quality: str = "native",
        format: str = "jpg"
    ) -> str:
        """
        构造 IIIF 图像 URL
        
        Args:
            ark: ARK 标识符或短 ID
            page: 页码，如 "f1", "f2"
            region: 区域 - "full" | "x,y,w,h" | "pct:x,y,w,h"
            size: 尺寸 - "full" | "w," | ",h" | "w,h" | "pct:n"
            rotation: 旋转角度 - 0, 90, 180, 270
            quality: 质量 - "native" | "gray" | "bitonal"
            format: 格式 - "jpg" | "png"
        
        Returns:
            完整的 IIIF 图像 URL
        """
        ark_id = self._extract_ark_id(ark)
        return f"{self.IIIF_BASE}/ark:/12148/{ark_id}/{page}/{region}/{size}/{rotation}/{quality}.{format}"
    
    def get_page_info(self, ark: str, page: str = "f1") -> Dict[str, Any]:
        """
        获取单页的详细信息（info.json）
        
        Args:
            ark: ARK 标识符或短 ID
            page: 页码，如 "f1"
        
        Returns:
            {
                "status": "success" | "error",
                "ark": str,
                "page": str,
                "width": int,
                "height": int,
                "image_url": str,
                "thumbnail_url": str
            }
        """
        ark_id = self._extract_ark_id(ark)
        info_url = f"{self.IIIF_BASE}/ark:/12148/{ark_id}/{page}/info.json"
        
        try:
            response = self._get(info_url)
            response.raise_for_status()
            info = response.json()
            
            return {
                "status": "success",
                "ark": ark_id,
                "page": page,
                "width": info.get("width"),
                "height": info.get("height"),
                "image_url": self.build_image_url(ark_id, page, size="full"),
                "thumbnail_url": self.build_image_url(ark_id, page, size=",300"),
                "medium_url": self.build_image_url(ark_id, page, size="1000,")
            }
        except Exception as e:
            return {"status": "error", "message": str(e), "ark": ark_id, "page": page}
    
    # ========== 辅助方法 ==========
    
    def _extract_ark_id(self, ark: str) -> str:
        """从各种格式中提取 ARK 短 ID"""
        if "ark:/12148/" in ark:
            return ark.split("ark:/12148/")[1].split("/")[0]
        return ark.strip()
    
    def get_gallica_url(self, ark: str) -> str:
        """获取 Gallica 在线阅读 URL"""
        ark_id = self._extract_ark_id(ark)
        return f"{self.GALLICA_BASE}/ark:/12148/{ark_id}"


# ========== 测试代码 ==========
if __name__ == "__main__":
    client = GallicaClient()
    
    print("=" * 60)
    print("测试 Gallica API 客户端")
    print("=" * 60)
    
    # 测试敦煌搜索
    print("\n【1. 搜索敦煌文献】")
    result = client.search_dunhuang(max_records=3)
    print(f"状态: {result['status']}")
    print(f"总记录数: {result['total_records']}")
    for rec in result.get('records', [])[:3]:
        print(f"  - {rec['title'][:50]}...")
        print(f"    ARK: {rec['ark']}")
        print(f"    Manifest: {rec['manifest_url']}")
    
    # 测试 Manifest（如果有结果）
    if result.get('records'):
        ark = result['records'][0]['ark']
        print(f"\n【2. 获取 Manifest: {ark}】")
        manifest_result = client.get_manifest(ark)
        print(f"状态: {manifest_result.get('status')}")
        print(f"标题: {manifest_result.get('title')}")
        print(f"总页数: {manifest_result.get('total_pages')}")
        if manifest_result.get('pages'):
            page = manifest_result['pages'][0]
            print(f"第1页缩略图: {page.get('thumbnail_url')}")
    
    print("\n" + "=" * 60)
    print("测试完成！")

