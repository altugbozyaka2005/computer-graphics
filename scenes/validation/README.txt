Validation scenes for the Module 1 report (each file's header explains what it tests).
renderReportedImages.sh renders all of them; scenes/tools/validate_module1.py turns the outputs into
the numbers quoted in the report (output/validation.log).

WSRT
  val_wsrt_pointlight.pbrt      point light on a matte plane vs Kd I cos(theta) / d^2, every pixel
  val_wsrt_filteredshadow.pbrt  shadow through a glass slab vs Kd I / d^2 (1 - F)^2
  val_wsrt_snell.pbrt           Snell's window: Fresnel transmission and total internal reflection
  val_wsrt_blinnphong.pbrt      Blinn-Phong parameter sweep (Ks, shininess, specular colour)
DRT
  val_drt_meshnormals.pbrt      the same OBJ torus with and without per-vertex normals; UVs from vt
  val_drt_penumbra.pbrt         area-light noise vs shadow rays (rendered with --lightsamples N --seed S)
  val_drt_furnace.pbrt          white furnace test of the Phong BRDF (energy conservation)
  val_dof_*.pbrt                aperture / focal distance sweep (world: include/drt_simple_world.pbrt)
Comparison and error handling
  pbrt/testscene_N.pbrt         standard pbrt-v4 scenes; pbrt-v4 reference images in pbrt/reference/,
                                pixels and thresholds in pbrt/testN.json
  errors/testscene_N.pbrt       18 deliberately broken scenes; each must give a descriptive error, no crash

Paths inside these scenes are relative to this directory (e.g. ../textures, ../meshes).
