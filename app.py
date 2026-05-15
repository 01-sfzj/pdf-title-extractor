import streamlit as st
import pdfplumber
import re
import io
import zipfile
from pathlib import Path

st.set_page_config(page_title="公文PDF标题提取器", layout="wide")
st.title("📄 公文PDF智能标题提取器")
st.markdown("上传PDF，系统会**自动猜测标题**（支持红头文件、通知、简报等），您可**手动修改**后下载。")

def extract_title_by_rules(text: str) -> str:
    """基于规则匹配常见公文标题模式"""
    if not text:
        return ""
    # 常见的公文标题模式
    patterns = [
        r"关于印发[《“][^》”]+[》”]的通知",      # 关于印发《xxx》的通知
        r"关于开展[^。]+的通知",                  # 关于开展xxx的通知
        r"关于[^。]+的通知",                      # 关于xxx的通知
        r"〔\d{4}〕\d+号[^。]+",                 # 文号+内容
        r"第\d+期[^。]+",                        # 简报第X期
        r"纠治[^。]+",                           # 纠治xxx
        r"燃气[^。]+",                           # 燃气相关
    ]
    for pat in patterns:
        match = re.search(pat, text)
        if match:
            title = match.group(0).strip()
            # 清理换行和多余空格
            title = re.sub(r'\s+', ' ', title)
            return title
    return ""

def extract_title_by_position(pdf_bytes: bytes) -> str:
    """基于位置：提取页面顶部区域的第一段文字"""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            if not pdf.pages:
                return ""
            page = pdf.pages[0]
            # 提取所有文本块，按y坐标排序
            words = page.extract_words()
            if not words:
                return ""
            # 找出最顶部的5个字符的y坐标
            min_y = min(w['top'] for w in words)
            # 收集顶部区域的文字（y坐标小于 min_y + 50）
            top_words = [w for w in words if w['top'] - min_y < 50]
            if not top_words:
                return ""
            top_words.sort(key=lambda w: (w['top'], w['x0']))
            title = " ".join(w['text'] for w in top_words)
            title = re.sub(r'\s+', ' ', title).strip()
            if len(title) < 5:
                return ""
            return title
    except:
        return ""

def extract_title_by_fontsize(pdf_bytes: bytes) -> str:
    """基于字体大小（如果可用）"""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            if not pdf.pages:
                return ""
            page = pdf.pages[0]
            chars = page.chars if hasattr(page, 'chars') else []
            if not chars:
                return ""
            sizes = [c['size'] for c in chars if c.get('size', 0) > 0]
            if not sizes:
                return ""
            max_size = max(sizes)
            # 排除可能为页眉的过大字体（比如 > 20 且出现在顶部边缘）
            if max_size > 30:
                # 可能不是标题，尝试次大字
                sizes.sort(reverse=True)
                max_size = sizes[1] if len(sizes) > 1 else max_size
            title_chars = [c for c in chars if c.get('size', 0) == max_size]
            title_chars.sort(key=lambda c: (c['y0'], c['x0']))
            title = "".join(c['text'] for c in title_chars).strip()
            return re.sub(r'\s+', ' ', title)
    except:
        return ""

def extract_title_comprehensive(pdf_bytes: bytes, file_name: str) -> str:
    """综合策略提取标题"""
    # 先尝试提取全文文本（用于规则匹配）
    full_text = ""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            full_text = "".join(p.extract_text() or "" for p in pdf.pages)
    except:
        pass
    
    # 1. 规则匹配
    title = extract_title_by_rules(full_text)
    if title:
        return title
    
    # 2. 基于位置（顶部区域）
    title = extract_title_by_position(pdf_bytes)
    if title and len(title) > 5:
        return title
    
    # 3. 基于字体大小
    title = extract_title_by_fontsize(pdf_bytes)
    if title and len(title) > 5:
        return title
    
    # 4. 回退：使用原始文件名（去掉扩展名）
    return Path(file_name).stem

def safe_filename(text: str) -> str:
    """过滤非法字符"""
    text = re.sub(r'[\\/*?:"<>|]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) > 100:
        text = text[:100]
    if not text:
        text = "未命名"
    return text

# UI部分
uploaded_files = st.file_uploader("上传PDF文件（支持多选）", type=['pdf'], accept_multiple_files=True)

if not uploaded_files:
    st.info("请上传PDF文件")
    st.stop()

st.subheader(f"已上传 {len(uploaded_files)} 个文件")

editable_titles = {}
original_names = {}

for idx, file in enumerate(uploaded_files):
    with st.expander(f"📄 {file.name}", expanded=True):
        # 智能提取标题
        pdf_bytes = file.getvalue()
        raw_title = extract_title_comprehensive(pdf_bytes, file.name)
        safe_title = safe_filename(raw_title)
        
        # 可编辑的标题输入框
        new_title = st.text_input(
            "文件名（可修改）",
            value=safe_title,
            key=f"title_{idx}"
        )
        editable_titles[file.name] = new_title
        
        # 下载单个
        st.download_button(
            label="⬇️ 下载此文件",
            data=pdf_bytes,
            file_name=f"{safe_filename(new_title)}.pdf",
            mime="application/pdf",
            key=f"down_{idx}"
        )

# 批量下载
if len(uploaded_files) > 1:
    st.subheader("📦 批量下载")
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for file in uploaded_files:
            new_title = editable_titles[file.name]
            final_name = f"{safe_filename(new_title)}.pdf"
            zip_file.writestr(final_name, file.getvalue())
    zip_buffer.seek(0)
    st.download_button(
        label="下载ZIP压缩包",
        data=zip_buffer,
        file_name="重命名后的文件.zip",
        mime="application/zip"
    )