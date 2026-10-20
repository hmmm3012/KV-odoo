# KV Odoo 18 — image built from this repository (addons + custom modules + odoo core)
FROM python:3.12-slim-bookworm

LABEL maintainer="KV Odoo" \
      description="Odoo 18 from source with custom addons"

ENV PYTHONUNBUFFERED=1 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gosu \
    gettext-base \
    build-essential \
    libpq-dev \
    libxml2-dev \
    libxslt1-dev \
    libldap2-dev \
    libsasl2-dev \
    libjpeg-dev \
    zlib1g-dev \
    libfreetype6-dev \
    liblcms2-dev \
    libwebp-dev \
    libtiff-dev \
    libopenjp2-7-dev \
    fonts-dejavu-core \
    postgresql-client \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-vie \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -ms /bin/bash odoo

WORKDIR /opt/odoo

COPY requirements.txt /opt/odoo/requirements.txt
COPY custom/kv_hr_contract/requirements.txt /tmp/kv_hr_contract-requirements.txt

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /opt/odoo/requirements.txt \
    && pip install --no-cache-dir -r /tmp/kv_hr_contract-requirements.txt

COPY custom/hr_attendance_portal/requirements.txt /tmp/hr_attendance_portal-requirements.txt
COPY custom/hr_employee_kv/requirements.txt /tmp/hr_employee_kv-requirements.txt
RUN pip install --no-cache-dir -r /tmp/hr_attendance_portal-requirements.txt \
    && pip install --no-cache-dir -r /tmp/hr_employee_kv-requirements.txt

COPY --chown=odoo:odoo . /opt/odoo

RUN chmod +x /opt/odoo/deploy/entrypoint.sh

USER root
EXPOSE 8069

ENTRYPOINT ["/opt/odoo/deploy/entrypoint.sh"]
CMD []
