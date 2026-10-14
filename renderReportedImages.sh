#!/bin/bash
# Builds the renderer, then renders every image shown in the Module 1 report into output/.
cd "$(dirname "$0")" || exit 1
echo "== building"
make -C source -j4 || { echo "build failed"; exit 1; }
R=./output/CGR26_renderer
FAILED=0
render() {  # render <scene-name> [extra renderer options...]
  local s=$1; shift
  printf "%-22s" "$s $*"
  if $R "scenes/$s.pbrt" --quiet "$@"; then echo " ok"; else echo " FAILED"; FAILED=$((FAILED + 1)); fi
}
echo "== Module 1"
for s in WSRT_simple WSRT_creative DRT_simple DRT_creative; do
  if [ -f "scenes/$s.pbrt" ]; then render "$s"; else echo "$s: scenes/$s.pbrt missing"; FAILED=$((FAILED + 1)); fi
done
echo "== feature checks: the same scenes with one parameter changed (each override is recorded in its log)"
for d in 1 2 3; do render WSRT_simple --maxdepth "$d" --out "WSRT_simple_md$d"; done
for n in 1 4 16; do render DRT_simple --spp 4 --lightsamples "$n" --out "DRT_simple_ls$n"; done
echo "== report figures (annotated images, insets, WSRT vs DRT, tone mapping, parameter checks)"
if [ -n "${PHOTO:-}" ]; then python3 scenes/tools/make_figures.py --photo "$PHOTO"; else python3 scenes/tools/make_figures.py; fi
echo
if [ $FAILED -eq 0 ]; then echo "all renders finished; images and logs are in output/, figures in output/figures/"; else echo "$FAILED render(s) failed or missing"; fi
exit $FAILED
