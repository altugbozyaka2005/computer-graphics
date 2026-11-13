Student test suite (CGR 2026, Module 3, 2.3.2)
==============================================

21 self-contained tests in three categories, compared against pbrt-v4:

  camera and intersections  test1 - test5    silhouettes at sub-pixel level, field-of-view framing
     1  orrery: sphere, clipped sphere (zmin/zmax/phimax), annulus, raised disk, triangles, icosahedron,
        stars a few pixels wide
     2  clockwork: Scale/Rotate petals, ConcatTransform, absolute Transform, mirror Scale -1 1 1,
        accumulated Rotate+Translate (spiral staircase), CoordinateSystem / CoordSysTransform
     3  field of view, landscape 2:1 (fov on the shorter, vertical axis)       [marker centroids]
     4  field of view, portrait 1:2 (fov on the horizontal axis)               [marker centroids]
     5  wide angle, fov 100: avenue of lamp posts, cables 0.02 thick, objects at 60-90 units and at the lens
  shading                   test6 - test9
     6  still life: Phong diffuse under a point light and a spotlight (cone and falloff), maxdepth 1
     7  chess endgame: rectangular and spherical area lights, soft shadows, smooth-shaded meshes
     8  gallery: closed room, interreflection (maxdepth 3), colour bleeding, indirect-only surfaces
     9  Phong specular lobes (exponents 12-200) under red, green and blue point lights: analytic reference
  error handling            test10 - test21  12 scenes with one deliberate error each, in six groups:
    syntax     10-11  misspelt directive, missing ]
    structure  12-13  AttributeEnd without AttributeBegin, missing Include file
    unknown    14-16  unknown shape type, unknown material type, undefined named material
    files      17     missing texture image
    transform  18     Translate with two numbers
    range      19-21  negative sphere radius, mesh index out of range, fov 200

Requirements: Python 3 (standard library only). Nothing else; pbrt-v4 is only needed to re-create the
references (scenes/tools/make_module3_tests.py in the CGR26_renderer submission).

Running
-------
  ./runAllTests.sh                              (or: python3 runAllTests.py)
      uses ../output/CGR26_renderer and looks for its outputs in ../output/
  python3 runAllTests.py --renderer /path/to/your/output/CGR26_renderer
  python3 runAllTests.py --tests 3,7,12         a subset;   testN/run.sh runs test N alone
  python3 runAllTests.py --outdir DIR           if your renderer writes somewhere other than its own folder
  python3 runAllTests.py --ldr-encoding linear  if your 8-bit PNG/PPM output is linear (not sRGB)
  python3 runAllTests.py --extra --spp 64       extra arguments passed to the renderer (must come last)

For every test the runner starts   <renderer> <abs path>/testN/testscene_N.pbrt   with testN/ as the
working directory, waits (default timeout 900 s per test) and then looks in the output folder for

  image: testsuite_my_N.pfm / .png / .ppm   or   testscene_N.pfm / .png / .ppm   (PFM preferred)
  log:   testsuite_my_N.log                 or   testscene_N.log  (the console output is used if absent)

(the scenes set Film "string filename" [ "testsuite_my_N.png" ]; renderers that name outputs after the
scene file are found too). Results: runAllTests.log (one line per test and a summary per category, with
the error tests also counted per group) and results/testN/ (copies of your image and log, the console
output, the reference and your image with the same display mapping, and difference images).

Conventions the scenes rely on
------------------------------
  - pbrt-v4 syntax; Integrator "distributed" (the image tests) with "integer maxdepth" as in pbrt's path
    integrator: maxdepth 1 = direct lighting only, 3 = direct + two indirect bounces.
  - Material "diffuse" "rgb reflectance" = Phong BRDF with Ks = 0 (kd / pi). Test 9 uses
    Material "phong" "rgb Kd" "rgb Ks" "float exponent" = kd/pi + ks (n+2)/(2 pi) cos^n(alpha),
    alpha = angle between the mirror direction and the light direction (normalised modified Phong).
  - Camera tests use glowing two-sided area lights ("bool twosided" true) on a black background. Every
    glowing object has the same luminance (only the hue differs), so a pixel's luminance is the fraction
    of it covered by objects; they need area lights to be visible to camera rays. PixelFilter "box": each pixel is the plain
    average of its samples.
  - Triangle meshes with "normal N" (tests 6 and 7) are smooth-shaded with interpolated normals.
  - The shading tests assume the sample counts given in each scene (Sampler, lightsamples): with far fewer
    samples Monte Carlo noise alone exceeds the thresholds. The camera tests are insensitive to this.
  - Linear radiance is compared. A PFM output is used as is; an 8-bit PNG/PPM is decoded from sRGB.
    If your renderer tone-maps (e.g. Reinhard) before writing PNG/PPM, the shading tests will fail for
    that reason alone: write PFM, or switch tone mapping off for these scenes.

Metrics and pass criteria (thresholds are in each testN/test.json)
-----------------------------------------------------------------
  camera, metric "coverage" (tests 1, 2, 5)
      coverage = pixel luminance / luminance of a fully covered pixel (98th percentile of non-black
      pixels of each image). A pixel is on the wrong side of an edge if the reference shows it < 25%
      covered and yours >= 50%, or > 75% and yours < 50% (partly covered reference pixels are not
      counted). Fails if more than max_mismatch of all pixels are wrong, or if the mean signed edge
      offset (sum of coverage differences / number of partly covered pixels, in pixels) exceeds
      max_offset: this catches a silhouette that is uniformly a fraction of a pixel too large/small.
      results/testN/diff_N.png: grey both, red yours only, cyan reference only.
  camera, metric "centroids" (tests 3, 4)
      nine small spheres at 5/50/95% of the width and 6/50/94% of the height; the luminance-weighted
      centroid of each is compared with the reference's. Fails above max_centroid_error pixels.
  shading, metric "pixels" (tests 6 - 9)
      at the listed pixels (labels in test.json say what each one shows), the mean over a
      (2*window+1)^2 block of yours and of the reference; error = max over r,g,b of
      |yours - ref| / max(luminance of ref, 5% of the reference's mean luminance). Fails above
      max_rel_error. The whole-image relative RMSE is reported for information.
  error (tests 10 - 21)
      passes if the renderer does not crash (killed by a signal / exit status >= 128) or hang, and its
      log or console output has an error/warning line that mentions one of the test's keywords.

Each test folder
----------------
  testscene_N.pbrt               the scene
  testscene_N_pbrt.pbrt          the same scene for pbrt-v4 (Integrator "path"; more samples; writes the
                                 reference) - not present for test 9, whose reference is analytic
  testsuite_ref_N.pfm / .png     reference image (linear HDR / clamped sRGB for viewing)
  testsuite_ref_N.log            reference log: pbrt-v4's console output (error tests: pbrt-v4's message)
  example_testsuite_my_N.log     the log CGR26_renderer writes for this scene (a passing log)
  test.json                      category (and group), metric, pixels or markers, keywords, thresholds
  run.sh                         runs this test only

pbrt-v4 has no Phong BRDF: the shading tests compare the Phong BRDF's diffuse term, which is pbrt-v4's
"diffuse" material, and test 9 checks the specular lobes against their closed form (with hard shadows,
box-filtered over each pixel). pbrt-v4 renders spectrally and these scenes are given in RGB, so expect
differences of a few tenths of a percent in saturated colours even for a correct renderer (the lights of
the pbrt-compared shading tests are white to keep this small). pbrt-v4's references are themselves
Monte Carlo estimates (64x64 or 128x128 samples per pixel).
