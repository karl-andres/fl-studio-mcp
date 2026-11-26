# Synthetic reference audio

These one-second 220 Hz sine tones were generated for format-validation tests; they contain no user recordings.

```sh
ffmpeg -f lavfi -i sine=frequency=220:duration=1 -c:a libmp3lame -q:a 9 reference.mp3
ffmpeg -f lavfi -i sine=frequency=220:duration=1 -c:a aac -b:a 32k reference.m4a
```

The fixtures are committed, so ffmpeg is not required to run the app or tests.
