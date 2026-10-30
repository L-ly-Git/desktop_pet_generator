# Flat Cartoon to 9 Parts

This tool decomposes one existing flat cartoon image into the shared contract v1
nine-part rig. It does not redraw or restyle the character. Output pixels are
copied from the source image, with only the small eye/mouth areas inpainted in
head.png so that blinking and mouth animation do not leave holes.

## Entry point

```bat
.venv\Scripts\python.exe tools\step2\flat_cartoon_split9.py ^
  --input "photo_cartoon_instance\source.png" ^
  --output-dir "photo_cartoon_instance\flat_char_01" ^
  --character-id flat_char_01 ^
  --name "Flat Character 01"
```

Options:

- `--fit-ratio 0.94`: character fit ratio on the 512 x 512 canvas.
- `--masks-dir DIR`: optional corrected part masks named after each part.
- `--debug-dir DIR`: writes foreground, semantic labels, masks, and stats.
- `--no-validate`: skips the contract validator.
- `--model PATH`: overrides the local ONNX face model.

## Output

```text
out/
  character.json
  parts/
    head.png
    body.png
    arm_l.png
    arm_r.png
    leg_l.png
    leg_r.png
    eye_l.png
    eye_r.png
    mouth.png
  preview.png
```

All parts are 512 x 512 full-canvas RGBA PNGs. Head includes the face, hair,
hat, and hair accessories. Preview is composited on a checkerboard.

## Pipeline

1. Use the input alpha when it contains meaningful transparency.
2. Otherwise detect the main warm character component, attach adjacent neutral
   highlights/shoes, close small holes, and reject detached neutral objects.
3. Crop the head area and run a local anime-face U-Net ONNX model.
4. Keep the two largest eye components and the largest mouth component.
5. Split the remaining foreground into head, dress/body, left/right arms, and
   left/right legs using clothing color, skin tone, hair tone, row extents, and
   proximity to semantic seeds.
6. Keep the head's main connected component. Detached dark fragments near
   the shoulders/arms are assigned to the nearest arm layer instead of leaking
   hand or arm outlines into head.png.
7. Inpaint only the eye/mouth regions in the head base layer.
8. Normalize the character into the 512 x 512 canvas, bottom-center aligned.
9. Derive pivots from the actual part masks and write character.json.
10. Run tools/validate.py against all shipped actions.

## First sample

- Input: photo_cartoon_instance/[screenshot].png
- Output: photo_cartoon_instance/flat_char_01/
- Character ID: flat_char_01
- Contract validation: PASS
- Visual checks: hat and hair are merged into head.png; eyes and mouth are
  independent; blink and yawn actions render without face holes.

## Reuse limits

- Automatic mode currently expects a character whose face/clothing colors are
  separable from the background, which is typical of flat cartoon references.
- Strongly overlapping arms, non-frontal poses, cropped limbs, or very unusual
  clothing may need corrected masks through --masks-dir.
- If a required part is empty, the tool stops with an explicit error instead of
  silently producing a broken rig.
- Manual masks are grayscale PNGs named exactly as the nine part files. They can
  be at source resolution or at any size; the tool resizes them to the source.

## Model and dependency paths

The runtime model is local:

- models/anime_face_seg/anime_face_unet.onnx
- Size: 6,209,229 bytes
- SHA-256: 619150282DFD211E7C822A31D2AD96E90BA380D7818FCF2A8AA759901719357D
- License copy: models/anime_face_seg/LICENSE.txt
- Upstream: https://github.com/siyeong0/Anime-Face-Segmentation

The model was exported to ONNX once with system PyTorch. ONNX export required
the system Python package onnx under D:\tools\python3.12\Lib\site-packages.
The runtime only needs project .venv with onnxruntime, OpenCV, NumPy, and
Pillow. It does not need PyTorch or the system onnx package.

The export also used the torchvision MobileNetV2 pretrained checkpoint cached at:

C:\Users\罗烈易\.cache\torch\hub\checkpoints\mobilenet_v2-b0353104.pth

The upstream source checkout used for export is kept for audit at:

artifacts/anime-face-seg-src/

## Tests

```bat
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The suite includes unit tests for foreground detection and canvas alignment,
plus an end-to-end test of the first flat sample.