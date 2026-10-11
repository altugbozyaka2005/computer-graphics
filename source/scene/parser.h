// Parser for the subset of the pbrt-v4 scene format supported by the renderer
// (pbrt-v4 Appendix C / https://pbrt.org/fileformat-v4). Errors are logged with
// file:line:column; recoverable problems fall back to defaults, fatal ones
// (e.g. a syntax error inside a token) make parseScene return false.
#pragma once

#include <string>

#include "scene.h"

bool parseScene(const std::string& path, Scene* scene);
