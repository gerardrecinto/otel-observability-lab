FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY checkout_demo.py .
USER 65532:65532
CMD ["python", "checkout_demo.py"]
