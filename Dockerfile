# 1. استخدام نسخة خفيفة ومستقرة من بايثون
FROM python:3.10-slim

# 2. تعيين متغيرات البيئة لضمان رؤية الـ Logs فوراً ومنع ملفات pyc
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# 3. تعيين مجلد العمل
WORKDIR /app

# 4. تثبيت أدوات النظام الضرورية
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 5. نسخ وتثبيت المكتبات (نفس طريقتك الذكية في الـ Caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. نسخ بقية الملفات
COPY . .

# 7. ملاحظة: Render سيقوم بضبط PORT تلقائياً، الكود في app.py 
# يجب أن يقرأ المنفذ من متغير البيئة (Environment Variable)

# 8. أمر التشغيل
CMD ["python", "app.py"]
