這是一份整理自 CBETA API 官方說明頁面的完整技術文檔。此文檔涵蓋了全文檢索、目錄檢索、高級語法、相似度檢索等多個 API 端點的使用規範。

---

# CBETA Search API 使用文檔

**Base URL**: `https://cbdata.dila.edu.tw/stable/`

本 API 提供對 CBETA 電子佛典集成（CBData）的檢索功能，支持全文檢索、目錄結構檢索、KWIC（關鍵詞在文中）顯示、異體字查詢及相似文本檢索等功能。

---

## 1. 核心檢索 API

### 1.1 一般全文檢索 (Full Text Search)
最基礎的全文檢索功能，支持組字式查詢。

*   **Endpoint**: `/search`
*   **Method**: `GET`
*   **URL 範例**: `https://cbdata.dila.edu.tw/stable/search?q=法鼓`

#### 參數說明
| 參數名稱 | 必填 | 說明 |
| :--- | :--- | :--- |
| `q` | 是 | 搜尋關鍵詞。支持組字式（如 `[幻-ㄠ+糸]`）。單引號需轉義 `\%27`。 |
| `fields` | 否 | 指定回傳欄位（如 `work,juan,term_hits`）。 |
| `rows` | 否 | 每頁回傳筆數，預設 20。 |
| `start` | 否 | 分頁起始位置，預設 0。 |
| `order` | 否 | 排序方式。支援多欄位排序（如 `time_from,work`），可用 `+` (升冪) 或 `-` (降冪)。<br>可用欄位：`canon` (藏經), `category` (部類), `juan` (卷), `vol` (冊), `work` (經號), `time_from`/`time_to` (年代), `term_hits` (詞頻)。 |

#### 回傳格式
回傳包含 `num_found` (總卷數), `total_term_hits` (總詞頻), 及 `results` (詳細列表)。

---

### 1.2 整合檢索 (All in One Search)
功能最強大的檢索端點，同時回傳 KWIC（前後文）、Facet（分類統計）及全文結果。

*   **Endpoint**: `/search/all_in_one`
*   **Method**: `GET`
*   **URL 範例**: `https://cbdata.dila.edu.tw/stable/search/all_in_one?q=法鼓&facet=1`

#### 參數說明
| 參數名稱 | 說明 |
| :--- | :--- |
| `q` | 搜尋關鍵詞（支援 **Extended Search** 高級語法，詳見下文）。 |
| `note` | `1` (預設): 含夾注；`0`: 不含夾注。 |
| `facet` | `1`: 回傳分類統計（藏經、部類、作譯者、朝代、佛典）；`0` (預設): 不回傳。 |
| `around` | KWIC 顯示的關鍵詞前後字數，預設 10。 |
| `rows` | 每頁回傳筆數，預設 20。 |
| `start` | 分頁起始位置，預設 0。 |
| `fields` | 指定回傳欄位。 |
| `cache` | `1` (預設): 使用快取；`0`: 不使用。 |

---

### 1.3 擴充檢索語法 (Extended Search Syntax)
適用於 `search/extended`、`search/all_in_one`、`search/notes` 等端點的高級查詢語法。

> **注意**：所有符號需進行 URL Encode。

| 功能 | 語法範例 | 說明 |
| :--- | :--- | :--- |
| **精確搜尋** | `"法鼓"` | 雙引號不可省略，強制精確匹配。 |
| **AND** | `"法鼓" "聖嚴"` | 空格表示 AND，兩詞皆須出現。 |
| **OR** | `"波羅蜜" \| "波羅密"` | 豎線 `\|` 表示 OR。 |
| **NOT** | `"迦葉" !"迦葉佛"` | 驚嘆號 `!` 表示排除後者。 |
| **NEAR** | `"法鼓" NEAR/7 "迦葉"` | 兩詞距離不超過 7 個字。 |
| **Exclude** | `"直心" -"正直心"` | 排除前搭配（Negative Lookbehind）。 |
| **Exclude** | `"舍利" -"舍利弗"` | 排除後搭配（Negative Lookahead）。 |

---

## 2. 特殊檢索 API

### 2.1 KWIC 檢索 (Keyword in Context)
針對**單卷**佛典進行檢索，並回傳前後文。常用於精確定位。

*   **Endpoint**: `/search/kwic`
*   **URL 範例**: `https://cbdata.dila.edu.tw/stable/search/kwic?work=T0001&juan=1&q=舍利`

#### 參數說明
| 參數名稱 | 必填 | 說明 |
| :--- | :--- | :--- |
| `work` | 是 | 佛典編號 (如 `T0001`)。 |
| `juan` | 是 | 卷號 (如 `1`)。 |
| `q` | 是 | 關鍵詞，多詞用逗號分隔。 |
| `note` | 否 | `1` (預設): 含夾注；`0`: 不含夾注（可跨夾注檢索）。 |
| `mark` | 否 | `1`: 關鍵字加 `<mark>` 標籤；`0` (預設): 不加。 |
| `sort` | 否 | `f` (預設): 依後文排序; `b`: 依前文排序; `location`: 依出現位置排序。 |

---

### 2.2 註解檢索 (Search Notes)
專門搜尋校勘條目、註解或夾注。

*   **Endpoint**: `/search/notes`
*   **URL 範例**: `https://cbdata.dila.edu.tw/stable/search/notes?q="阿含" NEAR/5 "迦葉"`

#### 特性
*   支援 **Extended Search** 語法（AND, OR, NOT, NEAR）。
*   `facet=1` 可回傳分類統計。
*   回傳欄位包含 `note_place` (foot/inline) 及 `highlight` (高亮內容)。

---

### 2.3 相似文本搜尋 (Similarity Search)
輸入一段長文本，尋找 CBETA 中相似的段落（基於 Smith-Waterman 演算法）。

*   **Endpoint**: `/search/similar`
*   **URL 範例**: `https://cbdata.dila.edu.tw/stable/search/similar?q=諸惡莫作，眾善奉行`

#### 參數說明
| 參數名稱 | 說明 |
| :--- | :--- |
| `q` | 搜尋字串（建議 6~50 字，不含標點）。 |
| `k` | 初步模糊搜尋取前 k 筆（預設 500）。 |
| `gain` | 匹配加分（預設 2）。 |
| `penalty` | 不匹配/插入/刪除扣分（預設 -1）。 |
| `score_min` | 最低分數門檻（預設 16）。 |

---

## 3. 輔助與元數據檢索

### 3.1 經目/目錄搜尋 (TOC Search)
搜尋經名、部類目錄或佛典內目次。

*   **Endpoint**: `/search/toc`
*   **URL 範例**: `https://cbdata.dila.edu.tw/stable/search/toc?q=阿含`
*   **回傳類型 (`type`)**:
    *   `catalog`: 部類目錄
    *   `work`: 佛典標題
    *   `toc`: 佛典內目次

### 3.2 佛典標題搜尋 (Title Search)
僅搜尋佛典標題（經名），支援模糊搜尋。

*   **Endpoint**: `/search/title`
*   **URL 範例**: `https://cbdata.dila.edu.tw/stable/search/title?q=觀無量壽經`

### 3.3 異體字查詢 (Variants)
列出關鍵詞的異體字變化，可用於前端製作「異體字建議」。

*   **Endpoint**: `/search/variants`
*   **URL 範例**: `https://cbdata.dila.edu.tw/stable/search/variants?q=著衣持鉢`
*   **參數**:
    *   `scope=title`: 僅列出佛典題名中的異體字。

### 3.4 簡體轉繁體搜尋 (Simplified Chinese Search)
輸入簡體字，系統自動轉為繁體後搜尋並回傳筆數。

*   **Endpoint**: `/search/sc`
*   **URL 範例**: `https://cbdata.dila.edu.tw/stable/search/sc?q=四圣谛`

### 3.5 統計面向 (Facet)
單獨獲取某個關鍵詞在不同維度下的統計數據。

*   **Endpoint**: `/search/facet` (回傳所有維度) 或 `/search/facet/{type}` (指定維度)
*   **Type**: `canon` (藏經), `category` (部類), `creator` (作譯者), `dynasty` (朝代), `work` (佛典)。
*   **URL 範例**: `https://cbdata.dila.edu.tw/stable/search/facet/dynasty?q=法鼓`

---

## 4. 限制搜尋範圍 (通用過濾器)
幾乎所有上述 API (如 `search`, `all_in_one`, `notes`, `similar`) 都支援以下過濾參數，用於縮小搜尋範圍：

| 參數 | 說明 | 範例 |
| :--- | :--- | :--- |
| `canon` | 限制藏經版本 | `canon=T` (大正藏) |
| `category` | 限制部類 | `category=阿含部類` |
| `vol` | 限制冊號 | `vol=T01` |
| `work` | 限制經號 | `work=T0001` |
| `creator` | 限制譯者 | `creator=A001519` |
| `time_from` | 起始年代 | `time_from=600` |
| `time_to` | 結束年代 | `time_to=900` |
| `dynasty` | 限制朝代 | `dynasty=唐` |

---

## 5. 狀態碼與錯誤處理
API 回傳標準 JSON 格式。
*   **200 OK**: 請求成功。
*   **Response 結構**: 通常包含 `time` (耗時), `num_found` (結果數), `results` (資料陣列)。