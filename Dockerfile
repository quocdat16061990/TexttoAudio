# 1. Chọn base image Python
FROM python:3.11-slim

# 2. Set thư mục làm việc bên trong container
WORKDIR /app

# 3. Copy file requirements và cài đặt
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copy toàn bộ source code vào container
COPY . /app

# 5. Mở port của Streamlit
EXPOSE 8501

# 6. Lệnh chạy Streamlit
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
