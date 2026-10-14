# CGR 2026 coursework renderer (`CGR26_renderer`): Module 1 checkpoint

A physically based renderer written in C++17 using only the C++ standard library.
It reads a subset of the pbrt-v4 scene format and contains two integrators,
selected by the scene's `Integrator` directive:

- `whitted`: Whitted-style ray tracer (WSRT).
- `distributed`: distributed ray tracer (DRT).

## Development and test environment

| | |
|---|---|
| OS | macOS 26.6.2 (Darwin 25.6.0) |
| Hardware | Apple M5 Pro, 15 CPU cores |
| Compiler | Apple clang 21.0.0 (clang-2100.1.1.101), target arm64-apple-darwin |
| Build system | GNU Make 3.81 (`source/Makefile`) |
| Flags | `-std=c++17 -O3 -Wall -Wextra -pedantic -pthread` (the build has no warnings) |

The code is portable C++17 and should also build with g++ ≥ 9 or clang ≥ 10 on Linux.

## Building

```sh
make -C source            # or: cd source && make
```

This produces `output/CGR26_renderer`. Object files go to `build/`.
Run `make -C source clean` to remove them.

Without `make`:

```sh
cd source
c++ -std=c++17 -O3 -pthread -o ../output/CGR26_renderer main.cpp core/*.cpp geometry/*.cpp render/*.cpp scene/*.cpp
```

## Running the renderer on a scene

```sh
./output/CGR26_renderer scenes/WSRT_simple.pbrt
```

Relative paths inside a scene (textures, meshes, `Include`) are resolved against the
scene file's directory. All outputs go to `output/`, i.e. the executable's directory.
`--outdir` changes this.

| File | Content |
|---|---|
| `<name>.png` | display image (tone mapped and sRGB encoded) |
| `<name>.pfm` | linear HDR radiance (a format pbrt-v4 can also write), for quantitative comparisons |
| `<name>.log` | parse warnings and errors (with `file:line:column`), the scene summary, per-stage timings (parse, render, output) and ray statistics |

`<name>` is the stem of the Film `"string filename"`. If the scene has none, the scene file's stem is used.

Exit codes:
- `0`: rendered, possibly with recoverable errors that are logged.
- `1`: fatal scene error such as a syntax error or a missing file, with no image produced. The log explains why.
- `2`: bad command line.
- `3`: internal error.

Command-line overrides (each is recorded in the log). See `--help` for the full list.

```
--spp N  --integrator whitted|distributed  --maxdepth N  --lightsamples N
--res WxH  --threads N  --seed N  --out NAME  --outdir DIR  --ppm  --quiet
```

## Rendering every reported image

```sh
./renderReportedImages.sh
```

The script builds the project and renders `WSRT_simple`, `WSRT_creative`, `DRT_simple` and
`DRT_creative` into `output/`.

Texture tools use only the Python 3 standard library:

```sh
python3 scenes/tools/make_textures.py                                    # regenerates scenes/textures/*.ppm
python3 scenes/tools/make_poolroom.py    # creative scenes: textures, meshes, include/poolhall_*.pbrt (--all: all 18 ball textures)
python3 scenes/tools/make_figures.py [--photo photo.png]   # report figures in output/figures/ (annotated
                                         # images, zoomed insets, WSRT vs DRT, photo vs render, and
                                         # clamp vs Reinhard tone mapping recomputed from the DRT .pfm);
                                         # --photo takes a PNG, e.g. from a phone JPEG:
                                         # sips -s format png --resampleHeightWidthMax 1600 photo.jpg --out photo.png
python3 scenes/tools/png2ppm.py photo.png scenes/textures/photo.ppm 512  # use a photo as a texture
```

## Supported scene format

**pbrt-v4 directives**

- **Transforms:** Identity, Translate, Scale, Rotate, LookAt, Transform, ConcatTransform,
  CoordinateSystem, CoordSysTransform, ReverseOrientation.
- **Render options:** Camera, Film, Sampler, Integrator.
- **Structure:** WorldBegin, AttributeBegin/End, TransformBegin/End.
- **Materials:** Material, MakeNamedMaterial, NamedMaterial.
- **Other:** Texture, LightSource, AreaLightSource, ObjectBegin/End, ObjectInstance, Include, Import.
- **Recognised and ignored with a warning:** PixelFilter, Accelerator, ColorSpace, Option,
  Attribute, media directives, TransformTimes, ActiveTransform.
- Any other directive, or a malformed one, is logged as an error with its location.

**Objects**

| Kind | Supported |
|---|---|
| Camera | `perspective` (`fov`, `lensradius`, `focaldistance`, `screenwindow`, `frameaspectratio`) |
| Shapes | `sphere` (partial spheres too), `disk`, `trianglemesh`, `bilinearmesh` (triangulated), `plymesh` (ascii and binary), plus the extensions `objmesh` and `plane`. Any shape can take an alpha cut-out mask (`"float alpha"` or `"texture alpha"`, threshold 0.5) that applies to camera and shadow rays |
| Lights | `point`, `spot`, `distant`, `infinite` (constant `L` only), and `AreaLightSource "diffuse"` on any finite shape |
| Materials | `diffuse`, `dielectric`, `conductor`, `interface`, an approximation of `coateddiffuse`, plus the extensions `phong`, `blinnphong` and `mirror` |
| Textures | `imagemap` (PPM/PFM), `checkerboard` (2D), `constant`, `scale`, `mix` |
| Sampler | `independent` (`pixelsamples`) |

**Renderer extensions**

These are not in pbrt-v4, so scenes that use them only work with this renderer.

- `Integrator "whitted"` and `Integrator "distributed"`.
  - `whitted`: `integer maxdepth`, `rgb ambient`, `bool transparentshadows` (default false: filtered
    shadow rays that pass through dielectrics, attenuated by Fresnel transmission and `Kt`).
  - `distributed`: `integer maxdepth`, `integer lightsamples` (shadow rays per area light).
    Optional for the DRT (all off by default):
    `bool transparentshadows` (filtered shadow rays through glass, as in the WSRT; light that reaches
    a lamp by refraction after a diffuse bounce is then not counted again),
    `float minweight` (stop a path once its throughput falls below this value, e.g. 0.001), and
    `bool caustics` (false: light reaching a lamp via a mirror or glass after a diffuse bounce is
    not counted; removes rare bright speckles at the cost of that light).
- `Material "blinnphong"` / `"phong"`:
  - `rgb Kd` or `texture Kd`
  - `rgb Ks`, `rgb Ka`, `rgb Kr`
  - `float shininess` (or `exponent`)
  - `bool normalized`
- `Material "mirror"`: `rgb Kr`.
- `Shape "plane"`: `point3 p`, `normal n`. The plane is infinite and gets planar UVs.
- `Shape "objmesh"`: `string filename`.
- Film tone mapping:
  - `string tonemap` (`reinhard` | `none`). The default is `reinhard` for the DRT and `none` for the WSRT.
  - `string tonemapmode` (`luminance` | `rgb`).
  - `float whitepoint` (0 = automatic, i.e. the maximum scene luminance).
  - `float key` (Reinhard's photographic key, 0 = off).
  - `float exposure`.
- `AreaLightSource "diffuse"` also accepts `integer samples`, a per-light override of `lightsamples`.
  `samples 0` makes a visible-only emitter: seen directly and in mirrors/glass, but it does not
  light the scene (for small decorative lights whose illumination is negligible).

## Known limitations

- There is no acceleration structure, so every ray is tested against every primitive.
  Large meshes therefore render slowly.
- Rendering is in RGB, not spectrally. Spectra (blackbody, named spectra, sampled spectra)
  are converted to RGB with an analytic CIE fit.
- Rough conductors and dielectrics are rendered as smooth ones. `coateddiffuse` and named
  metals are approximations (all logged). Media, displacement and normal maps,
  environment maps, and image area lights are not supported.
- Image textures must be PPM (P2/P3/P5/P6) or PFM. PNG and EXR are not read.
- In the WSRT, area lights act as point lights at their centroid (hard shadows). Dielectrics cast
  opaque shadows unless `transparentshadows` is on; even then the shadow rays travel in straight
  lines, so refraction caustics (focused light) are not produced.
- Alpha masks: only a shape's nearest hit is tested against the mask (exact for triangles).
