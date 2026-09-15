# 내레이션 목소리

`vd_female_calm_ref.wav` — 내레이션 목소리의 기준 음성(9.4초). 사람 목소리를 녹음한 것이 아니라
Qwen3-TTS VoiceDesign 모델로 지어낸 목소리다. `narrate.py --engine qwen` 이 이 파일을
Qwen3-TTS Base 모델로 복제해 문단마다 같은 목소리로 읽힌다.

만든 설정 (Qwen3-TTS-12Hz-1.7B-VoiceDesign, seed 42, language Korean):

- instruct: "A calm, clear female narrator in her early 30s, speaking standard Seoul Korean at a
  moderate, steady pace. Honest and matter-of-fact, like reading a well-written user manual.
  Warm but restrained, no dramatic emphasis, not salesy, not alarming."
- 읽힌 문장(복제할 때 ref-text 로도 쓴다):
  "이 화면에서는 서버에서 일어난 일을 시간 순서대로 확인할 수 있습니다. 필요한 항목을 누르면 자세한 내용이 열립니다."

2026-09-14 OpenAI marin 과 Qwen3-TTS 샘플들을 들어 보고 이 목소리로 정했다.

## 전체 내레이션을 이 목소리로 다시 만들기

GPU 번호는 nvidia-smi 기준(비어 있는 카드를 고른다). 약 25분 분량을 두 장으로 15~20분.

```bash
python3 narrate.py --engine qwen --gpus 0,3 --force -- \
  --model /data/Source/Qwen3-TTS/models/Qwen3-TTS-12Hz-1.7B-Base \
  --ref-audio "$PWD/voice/vd_female_calm_ref.wav" \
  --ref-text "이 화면에서는 서버에서 일어난 일을 시간 순서대로 확인할 수 있습니다. 필요한 항목을 누르면 자세한 내용이 열립니다." \
  --seed 42 --language Korean
python3 verify_narration.py          # 빠진 문장이 있는지 받아쓰기로 대조
python3 build_frames.py
```

원고를 고친 뒤에는 `--force` 없이 같은 명령을 돌리면 바뀐 문단만 다시 만든다.
