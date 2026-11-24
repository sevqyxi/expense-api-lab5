FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# контракт gRPC і згенеровані Python stubs (protoc запускається під час збирання образу)
COPY proto ./proto
RUN python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. proto/auth.proto

COPY user_service/ .

ENV PYTHONUNBUFFERED=1
EXPOSE 8000 50051
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
