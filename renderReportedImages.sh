#!/bin/bash
# Builds the renderer, then renders every image shown in the Module 1 and Module 2 reports into
# output/, runs the quantitative checks quoted in the reports and makes the figures.
#   ./renderReportedImages.sh        both modules
#   ./renderReportedImages.sh 1      Module 1 only (output/, output/validation.log, output/figures/)
#   ./renderReportedImages.sh 2      Module 2 only (output/, output/module2/, output/figures/module2/)
cd "$(dirname "$0")" || exit 1
WHICH=${1:-all}
case "$WHICH" in all|1|2) ;; *) echo "usage: $0 [1|2]"; exit 2 ;; esac
echo "== building"
make -C source -j4 || { echo "build failed"; exit 1; }
R=./output/CGR26_renderer
FAILED=0
render() {  # render <scene-name> [extra renderer options...]
  local s=$1; shift
  printf "%-22s" "$s $*"
  if $R "scenes/$s.pbrt" --quiet "$@"; then echo " ok"; else echo " FAILED"; FAILED=$((FAILED + 1)); fi
}
if [ "$WHICH" != 2 ]; then
echo "== Module 1"
for s in WSRT_simple WSRT_creative DRT_simple DRT_creative; do
  if [ -f "scenes/$s.pbrt" ]; then render "$s"; else echo "$s: scenes/$s.pbrt missing"; FAILED=$((FAILED + 1)); fi
done
echo "== feature checks: the same scenes with one parameter changed (each override is recorded in its log)"
for d in 1 2 3; do render WSRT_simple --maxdepth "$d" --out "WSRT_simple_md$d"; done
for n in 1 4 16; do render DRT_simple --spp 4 --lightsamples "$n" --out "DRT_simple_ls$n"; done
echo "== validation scenes (scenes/validation, Module 1 report sections 2-4)"
rv() {  # rv <scene-name> [extra renderer options...]
  local s=$1; shift
  printf "%-40s" "$s $*"
  if $R "scenes/validation/$s.pbrt" --quiet "$@"; then echo " ok"; else echo " FAILED"; FAILED=$((FAILED + 1)); fi
}
for s in val_wsrt_pointlight val_wsrt_filteredshadow val_wsrt_snell val_wsrt_blinnphong val_drt_furnace val_drt_meshnormals \
         val_dof_pinhole val_dof_r010_f8 val_dof_r030_f8 val_dof_r010_f5; do rv "$s"; done
for n in 1 4 16 64 256 1024; do for seed in 1 2; do
  rv val_drt_penumbra --lightsamples "$n" --seed "$seed" --out "val_drt_penumbra_ls${n}_s$seed"
done; done
for n in 1 2 4 5 6 7 8; do  # pbrt-v4 comparison scenes (references in scenes/validation/pbrt/reference)
  printf "%-40s" "pbrt/testscene_$n"
  if $R "scenes/validation/pbrt/testscene_$n.pbrt" --quiet --out "val_pbrt_$n"; then echo " ok"; else echo " FAILED"; FAILED=$((FAILED + 1)); fi
done
echo "== quantitative checks (writes output/validation.log; also runs the 18 broken scenes)"
python3 scenes/tools/validate_module1.py --renderer "$R" --outdir output | grep -E "^==|PASS|FAIL"
echo "== report figures (annotated images, insets, WSRT vs DRT, tone mapping, parameter checks)"
if [ -n "${PHOTO:-}" ]; then python3 scenes/tools/make_figures.py --photo "$PHOTO"; else python3 scenes/tools/make_figures.py; fi
fi
if [ "$WHICH" != 1 ]; then
  echo "== Module 2: renders and measurements (output/module2/module2.log)"
  python3 scenes/tools/module2_study.py || FAILED=$((FAILED + 1))
  echo "== Module 2: feature checks (output/module2/validation.log)"
  V2=$(python3 scenes/tools/validate_module2.py); V2RC=$?
  echo "$V2" | grep -E "^(PASS|FAIL|==)"
  [ $V2RC -eq 0 ] || FAILED=$((FAILED + 1))
  echo "== Module 2: figures (output/figures/module2/)"
  python3 scenes/tools/make_figures_m2.py > /dev/null || FAILED=$((FAILED + 1))
fi
echo
if [ $FAILED -eq 0 ]; then echo "all renders finished; images and logs are in output/, figures in output/figures/"; else echo "$FAILED render(s) failed or missing"; fi
exit $FAILED
