# PDF 에디터

PDF를 열어서 직접 수정하고, 인쇄하거나 Word(.docx) / 한글(.hwpx)로 저장하는 Windows 데스크톱 프로그램입니다.

## 기능

- PDF 보기: 연속 스크롤, 확대/축소, 쪽 미리보기 창
- 텍스트 수정(글자를 클릭해서 고치기), 텍스트 상자 / 이미지 / 도형 추가, 실행 취소
- 인쇄 및 인쇄 미리보기
- Word(.docx), 한글(.hwpx)로 저장

## 실행 방법

### 1. 소스에서 실행

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python main.py [파일.pdf]
```

테스트는 먼저 샘플 PDF를 만든 뒤 실행합니다. (Windows의 맑은 고딕 글꼴을 사용하므로 샘플 파일은 저장소에 포함하지 않습니다.)

```bash
.venv\Scripts\python make_sample.py sample.pdf
.venv\Scripts\python test_core.py
```

### 2. exe로 만들기

```bash
.venv\Scripts\pip install pyinstaller
.venv\Scripts\python -m PyInstaller --noconfirm --windowed --name PDFEditor ^
  --collect-all pdf2docx --collect-all hwpx --collect-data docx --hidden-import fitz main.py
```

## 알려진 한계

- 텍스트는 줄 단위로 수정되며, 새로 넣은 글자는 사용자 PC의 맑은 고딕으로 표시됩니다.
- 스캔(이미지) PDF의 글자는 수정할 수 없습니다. (OCR 미지원)
- 변환 결과는 원본과 완전히 같지 않을 수 있습니다. 표나 다단 문서는 특히 그렇습니다.
- `.hwp` 저장은 지원하지 않으며, `.hwpx`는 한글 프로그램에서 열어 확인하지 못했습니다.

## 라이선스

이 프로그램은 [GNU AGPL-3.0](LICENSE)으로 배포됩니다. (PyMuPDF가 AGPL이기 때문입니다.)
사용한 라이브러리의 라이선스는 [NOTICE.md](NOTICE.md)를 참고하세요.
