#!/usr/bin/env bash
# exit on error
set -o errexit
# 파이썬 의존성 설치
pip install -r requirements.txt
# 브라우저 파일만 설치 (시스템 라이브러리 설치 시도인 install-deps 제거)
playwright install chromium