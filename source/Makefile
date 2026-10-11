# Build: make -C source        (or: cd source && make)
# Produces ../output/CGR26_renderer.
CXX      ?= c++
CXXFLAGS ?= -std=c++17 -O3 -Wall -Wextra -pedantic
LDFLAGS  ?= -pthread
OUT      := ../output
OBJDIR   := ../build

SRC := main.cpp \
	core/transform.cpp core/image.cpp core/log.cpp \
	geometry/shape.cpp \
	render/texture.cpp render/light.cpp render/camera.cpp \
	render/integrators.cpp render/renderer.cpp \
	scene/scene.cpp scene/params.cpp scene/meshio.cpp scene/parser.cpp \
	scene/builders_options.cpp scene/builders_world.cpp scene/builders_lights.cpp scene/builders_shapes.cpp
OBJ := $(SRC:%.cpp=$(OBJDIR)/%.o)

all: $(OUT)/CGR26_renderer

$(OUT)/CGR26_renderer: $(OBJ)
	@mkdir -p $(OUT)
	$(CXX) $(CXXFLAGS) -o $@ $^ $(LDFLAGS)

$(OBJDIR)/%.o: %.cpp
	@mkdir -p $(dir $@)
	$(CXX) $(CXXFLAGS) -MMD -MP -c $< -o $@

clean:
	rm -rf $(OBJDIR) $(OUT)/CGR26_renderer

-include $(OBJ:.o=.d)

.PHONY: all clean
