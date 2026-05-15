import streamlit as st
import pdfplumber
import re
import os
import tempfile
from pathlib import Path
import zipfile
import io

st.set_page_config(page_title="PDF标题提取器", layout="wide")
st.title("📄 PDF标题自动提取器")
st.markdown("上传PDF文件，系统将自动提取第一页**字号最大**的文本作为推荐标题，您可以手动调整后下载重命名的文件。")

def extract_title_from_pdf(pdf_bytes: bytes) -> str:
    """从PDF字节流中提取标题（基于最大字号）"""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            if not pdf.pages:
                return ""
            page = pdf.pages[0]
            chars = page.chars if hasattr(page, 'chars') else []
            if not chars:
                # 无字体信息，回退到第一行文本
                text = page.extract_text()
                if text:
                    first_line = text.strip().split('\n')[0]
                    return clean_title(first_line)
                return ""
            sizes = [c['size'] for c in chars if c.get('size', 0) > 0]
            if not sizes:
                return ""
            max_size = max(sizes)
            title_chars = [c for c in chars if c.get('size', 0) == max_size]
            title_chars.sort(key=lambda c: (c['y0'], c['x0']))
            title = "".join(c['text'] for c in title_chars).strip()
            return clean_title(title)
    except Exception as e:
        st.warning(f"提取失败：{e}")
        return ""

def clean_title(text: str) -> str:
    """清洗标题，过滤非法文件名字符"""
    if not text:
        return "未命名"
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'[\\/*?:"<>|]', '', text)
    if len(text) > 100:
        text = text[:100]
    return text

# 文件上传区域
uploaded_files = st.file_uploader("上传PDF文件（支持多选）", type=['pdf'], accept_multiple_files=True)

if not uploaded_files:
    st.info("请上传PDF文件")
    st.stop()

st.subheader(f"已上传 {len(uploaded_files)} 个文件")

# 存储每个文件的新标题
new_titles = {}
original_names = {}

col1, col2 = st.columns([1, 1])

for idx, file in enumerate(uploaded_files):
    with st.container():
        st.markdown(f"**文件 {idx+1}**：{file.name}")
        # 提取标题（缓存结果避免重复解析）
        if file.name not in new_titles:
            pdf_bytes = file.getvalue()
            title = extract_title_from_pdf(pdf_bytes)
            original_names[file.name] = title if title else file.name.rsplit('.', 1)[0]
        else:
            title = new_titles[file.name]
        
        # 可编辑的标题输入框
        new_title = st.text_input(
            f"建议标题（可修改）",
            value=original_names.get(file.name, title),
            key=f"title_{idx}_{file.name}"
        )
        new_titles[file.name] = new_title
        
        # 下载单个文件按钮
        pdf_data = file.getvalue()
        final_name = f"{new_title}.pdf"
        st.download_button(
            label="📥 下载此文件",
            data=pdf_data,
            file_name=final_name,
            mime="application/pdf",
            key=f"down_{idx}"
        )
        st.markdown("---")

# 批量下载为ZIP
if len(uploaded_files) > 1:
    st.subheader("批量下载")
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for file in uploaded_files:
            new_title = new_titles[file.name]
            final_name = f"{new_title}.pdf"
            zip_file.writestr(final_name, file.getvalue())
    zip_buffer.seek(0)
    st.download_button(
        label="📦 打包下载全部（ZIP）",
        data=zip_buffer,
        file_name="重命名后的文件.zip",
        mime="application/zip"
    )
