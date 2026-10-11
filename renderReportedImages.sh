#!/bin/bash
# Builds the renderer, then renders every image shown in the Module 1 report into output/.
cd "$(dirname "$0")" || exit 1
echo "== building"
make -C source -j4 || { echo "build failed"; exit 1; }
R=./output/CGR26_renderer
FAILED=0
render() {  # render <scene-name> [extra renderer options...]
  local s=$1; shift
  printf "%-22s" "$s"
  if $R "scenes/$s.pbrt" --quiet "$@"; then echo " ok"; else echo " FAILED"; FAILED=$((FAILED + 1)); fi
}
echo "== Module 1"
for s in WSRT_simple WSRT_creative DRT_simple DRT_creative; do
  if [ -f "scenes/$s.pbrt" ]; then render "$s"; else echo "$s: scenes/$s.pbrt missing"; FAILED=$((FAILED + 1)); fi
done
echo
if [ $FAILED -eq 0 ]; then echo "all renders finished; images and logs are in output/"; else echo "$FAILED render(s) failed or missing"; fi
exit $FAILED
