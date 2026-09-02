# Dante's Inferno Asset Tool

A Python tool for extracting and repacking game assets from Dante's Inferno
(Xbox 360) for upscaling and modification.

## Features

- **BIG/VIV archive parsing** - Read and write EA Visceral BIGH archives
  (`bigfile0.viv`, `bigfile1.viv`) with streaming I/O for multi-gigabyte files
- **STR/StreamSet unpacking** - Extract nested `.str` containers with
  RefPack decompression (`ols3`/`SHOC`/`SHDR`/`SDAT`/`Rpak`/`FILL` blocks)
- **STR repacking** - Rebuild `.str` files from extracted sub-files,
  preserving original header metadata
- **Texture conversion** - Convert TG4D/DXT1/DXT5 textures to DDS and PNG,
  using TG4H header files for dimension/format detection
- **Video extraction** - Extract VP6 video files (`.vp6`) from archives
- **Model extraction** - Extract EAGM mesh data (`.geo.Mesh`) from STR containers
- **Filelist support** - Map hashed archive entries back to original filenames
  using Gibbed.Visceral filelists
- **Full pipeline** - One-command extraction: BIG -> STR -> textures (PNG/DDS)

## Requirements

- Python 3.10+
- Pillow (`pip install pillow`) - PNG export
- texture2ddecoder (`pip install texture2ddecoder`) - Fast DXT decompression
  (optional; falls back to pure-Python decoder)

## Usage

### List archive contents

```powershell
python tools/asset_tool.py list game/bigfile0.viv
```

With filelist matching (auto-detected from `tools/Gibbed.Visceral/`):

```powershell
python tools/asset_tool.py list game/bigfile0.viv --filelist tools/Gibbed.Visceral/bin/projects/Dante's\ Inferno/files/BIGFILE1.filelist
```

### Extract videos

```powershell
python tools/asset_tool.py extract game/bigfile0.viv output_videos --type videos
```

### Extract everything (full pipeline with texture conversion)

```powershell
python tools/asset_tool.py extract game/bigfile0.viv output_all --full-pipeline
```

This extracts all files, unpacks STR containers, and converts textures to
DDS + PNG. Output structure:

```
output_all/
  _raw/              # Raw files from BIG archive
    levels/...       # STR files and other assets
    movies/...       # VP6 videos
  assets/            # Processed assets
    tg4d/            # Converted textures (DDS + PNG)
    models/          # EAGM mesh data
    videos/          # VP6 videos
```

### Extract and unpack STR files

```powershell
python tools/asset_tool.py extract game/bigfile0.viv output_dir --unpack-str
```

### Unpack a single STR file

```powershell
python tools/asset_tool.py unpack-str input.str output_dir/
```

Output includes `@metadata.json` with all stream header info for repacking.

### Repack a STR file

```powershell
python tools/asset_tool.py pack-str input_dir/ output.str
```

The input directory must contain `@metadata.json` from unpacking.

### Convert a texture

```powershell
# TG4D -> PNG (with TG4H header for dimensions)
python tools/asset_tool.py convert-texture texture.tg4d texture.png --tg4h texture.tg4h

# TG4D -> DDS
python tools/asset_tool.py convert-texture texture.tg4d texture.dds --tg4h texture.tg4h

# Without TG4H (auto-detect from file size)
python tools/asset_tool.py convert-texture texture.tg4d texture.png --width 256 --height 256
```

### Make a texture (for repacking)

```powershell
# PNG -> TG4D (DXT5)
python tools/asset_tool.py make-texture upscaled.png output.tg4d --format dxt5

# DDS -> TG4D
python tools/asset_tool.py make-texture upscaled.dds output.tg4d
```

### Pack a BIG archive

```powershell
python tools/asset_tool.py pack-big input_dir/ output.viv
```

## Asset types

The tool handles these asset types found in the game:

| Type | Extension | Format | Conversion |
|------|-----------|--------|------------|
| Textures | `.tg4d` | DXT1/DXT5 (BC1/BC3) | DDS, PNG |
| Texture headers | `.tg4h` | Visceral TG4H | Metadata for TG4D |
| Videos | `.vp6` | EA VP6 | Raw extraction |
| Meshes | `.geo.Mesh` | EAGM (proprietary) | Raw extraction |
| Audio | `.sbk.SBK` | Sound bank | Raw extraction |
| Models | `.simgroup` | SimGroup | Raw extraction |
| Animations | `.AnimationBank` | Visceral | Raw extraction |

## Format details

### BIG/VIV (BIGH)

- Magic: `BIGH` (0x42494748)
- Mixed endianness: total size is little-endian, all other fields big-endian
- 16-byte header: magic, total_size (LE), num_files (BE), header_size (BE)
- 12-byte entries: offset (BE), size (BE), name_hash (BE)
- 8-byte trailer: 0x4C323833, 0x15050000
- Data aligned to 2048-byte boundaries
- Filenames hashed with: `hash = hash * 65599 + char` (lowercase, backslash)

### STR (StreamSet)

- Magic: `ols3` (0x6F6C7333), big-endian
- Options block: 12 bytes (type, size, two u16 values)
- Content blocks: `SHOC` containing `SHDR`/`SDAT`/`Rpak` sub-blocks
- `SHDR`: stream metadata (build ID, dimensions, type, filenames)
- `SDAT`: uncompressed stream data
- `Rpak`: RefPack-compressed data (4-byte size prefix + compressed payload)
- `FILL`: padding blocks

### TG4H/TG4D (Textures)

- TG4H: texture header with metadata
  - Offset 0x20: u8 width_log (width = 2^(val+7))
  - Offset 0x22: u8 height_log (height = 2^(val+7))
  - Offset 0x26: u8 mipmap_count
  - Offset 0x27: u8 format_type (4=DXT5, 5=DXT1)
  - Variable: DXT format string ("DXT1", "DXT5", "DXT5_NM")
- TG4D: raw DXT-compressed pixel data (no header)

### EAGM (Meshes)

- Magic: `EAGM` (EA Geometry/Mesh)
- Proprietary format containing vertex data, indices, materials
- Bounding box at offset 0xA0 (6 floats: min XYZ, max XYZ)
- Full format requires further reverse engineering for OBJ/glTF export

## Workflow for upscaling textures

1. Extract assets:
   ```powershell
   python tools/asset_tool.py extract game/bigfile0.viv extracted --full-pipeline
   ```

2. Find the PNG files you want to upscale in `extracted/assets/`

3. Upscale with your preferred tool (Topaz, ESRGAN, etc.)

4. Convert back to TG4D:
   ```powershell
   python tools/asset_tool.py make-texture upscaled.png output.tg4d --format dxt5
   ```

5. Replace the TG4D file in the unpacked STR directory

6. Repack the STR:
   ```powershell
   python tools/asset_tool.py pack-str unpacked_str/ repacked.str
   ```

7. Replace the STR in the BIG archive and repack:
   ```powershell
   python tools/asset_tool.py pack-big extracted/ repacked.viv
   ```

## Limitations

- **RefPack compression** is implemented but may not match original compression
  ratios exactly. Rebuilt STR files will be larger but should be valid.
- **EAGM mesh format** is extracted as raw data only. Full mesh parsing
  (vertices, UVs, materials) requires additional reverse engineering.
- **VP6 video** is extracted as raw VP6 streams. Re-encoding requires a VP6
  encoder; transcoding to MP4 and back may not preserve game compatibility.
- **Filelist coverage** is partial (~396 of 2151 entries in bigfile0.viv are
  matched). Unknown entries are named `__UNKNOWN_0x{hash}`.
- **TG4H/TG4D pairing** uses filename matching. Some textures may not find
  their headers if naming conventions differ.

## Attribution

Format research based on [Gibbed.Visceral](https://github.com/gibbed/Gibbed.Visceral)
by Rick Gibbed (Zlib license). This tool reimplements the formats in Python
rather than copying the original C# source.
