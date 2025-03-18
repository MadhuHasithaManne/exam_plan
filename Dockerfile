# ✅ Use an official Python image as base
FROM python:3.11-slim  

# ✅ Set the working directory inside the container
WORKDIR /app

# ✅ Debug: Print system info
RUN echo "🔥 Starting Docker Build..." && uname -a && lsb_release -a || echo "Skipping lsb_release"

# ✅ Install system dependencies (LibreOffice for PDF generation)
RUN apt-get update && \
    echo "📦 Installing LibreOffice..." && \
    apt-get install -y libreoffice libreoffice-writer && \
    echo "✅ LibreOffice Installed Successfully!" && \
    rm -rf /var/lib/apt/lists/*

# ✅ Debug: Check LibreOffice installation
RUN which soffice && soffice --version || echo "❌ LibreOffice is NOT installed!"

# ✅ Copy only requirements.txt first for efficient caching
COPY requirements.txt .

# ✅ Install Python dependencies
RUN echo "📦 Installing Python Dependencies..." && pip install --no-cache-dir -r requirements.txt
COPY calibri.ttf /usr/share/fonts/truetype/calibri.ttf
RUN fc-cache -fv


# ✅ Copy the entire project files into the container
COPY . .

# ✅ Debug: List project files
RUN echo "📂 Project Files:" && ls -l /app

# ✅ Expose the Flask port (default: 5000, Render expects: 10000)
EXPOSE 10000

# ✅ Set the default command to run the app
CMD ["gunicorn", "app:app", "--timeout", "300", "--workers", "1"]
