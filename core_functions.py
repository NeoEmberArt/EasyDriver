
import bpy
import math
import re
import json
import mathutils
from math import degrees, radians

#---------------------------------------
# Driver Functions
#---------------------------------------

# Every driver Easy Driver creates gets a hidden marker appended as a trailing
# Python comment on the expression string. This is invisible to the math
# (comments are stripped before eval) but lets us reliably re-identify our
# own drivers later - including after the file has been closed and reopened,
# since it's just literal text saved in the .blend, not addon runtime state.
EASYDRIVER_MARKER = "EZDRV_V1"
_EZDRV_MARKER_RE = re.compile(r'#\s*' + re.escape(EASYDRIVER_MARKER) + r':([A-Z]+)')

def createDriver(armature_name, from_path, fromMin, fromMax, to_path, toMin, toMax, selfRotation=False, isDegrees=False, curve_type='LINEAR', source_space='LOCAL_SPACE'):
    """Create a driver from one bone/property to another with the chosen curve mapping and (optionally) clamping."""
    
    print(f"=== DRIVER CREATION START ===")
    print(f"FROM: {from_path}")
    print(f"TO: {to_path}")
    print(f"FROM RANGE: {fromMin} to {fromMax}")
    print(f"TO RANGE: {toMin} to {toMax}")
    print(f"CURVE TYPE: {curve_type}")
    
    # Convert degrees if needed
    if isDegrees:
        toMin = math.radians(toMin)
        toMax = math.radians(toMax)
    toMax = toMax + 0.0001 #small buffer value
    # Store original values for proper mapping
    original_fromMin, original_fromMax = fromMin, fromMax
    original_toMin, original_toMax = toMin, toMax
    
    # Normalize FROM range if reversed (for clamping purposes)
    if fromMin > fromMax:
        fromMin, fromMax = fromMax, fromMin
        print(f"INFO: Normalized FROM range for clamping: {fromMin} to {fromMax}")
    
    try:
        # === PARSE TARGET PATH ===
        print("\n=== PARSING TARGET PATH ===")
        target_data_block, target_data_path, to_index = parse_target_path(to_path)
        
        if not target_data_block:
            print("ERROR: Failed to parse target path")
            return False
        
        print(f"✓ Target parsed - Block: {target_data_block}, Path: {target_data_path}, Index: {to_index}")

        # === PARSE SOURCE PATH ===
        print("\n=== PARSING SOURCE PATH ===")
        source_config = parse_source_path(from_path, armature_name)
        
        if not source_config:
            print("ERROR: Failed to parse source path")
            return False

        # Only bone/object transform sources have a meaningful space concept
        if source_config.get('type') in ('bone', 'object'):
            source_config['space'] = source_space

        print(f"✓ Source parsed successfully")

        # === REMOVE OLD DRIVER ===
        print("\n=== REMOVING OLD DRIVER ===")
        remove_existing_driver(target_data_block, target_data_path, to_index)

        # === ADD NEW DRIVER ===
        print("\n=== ADDING NEW DRIVER ===")
        fcurve = add_new_driver(target_data_block, target_data_path, to_index)
        
        if not fcurve:
            print("ERROR: Failed to add driver")
            return False

        # === CONFIGURE DRIVER ===
        print("\n=== CONFIGURING DRIVER ===")
        if not configure_driver(fcurve, source_config):
            print("ERROR: Failed to configure driver")
            return False

        # === CREATE EXPRESSION ===
        print("\n=== CREATING EXPRESSION ===")
        expression = create_mapping_expression(original_fromMin, original_fromMax, original_toMin, original_toMax, curve_type)
        
        if not expression:
            print("ERROR: Failed to create expression")
            return False
        
        fcurve.driver.expression = expression + f"  # {EASYDRIVER_MARKER}:{curve_type.upper()}"
        print(f"✓ Expression: {expression}")

        # === FINALIZE ===
        print("\n=== FINALIZING ===")
        bpy.context.view_layer.update()
        
        print(f"✓ SUCCESS: Driver created!")
        print("=== DRIVER CREATION COMPLETE ===")
        
        return True
        
    except Exception as e:
        print(f"ERROR: Exception in createDriver: {e}")
        import traceback
        traceback.print_exc()
        return False


def createMultiSourceDriver(slots, combine_mode, fromMin, fromMax, to_path, toMin, toMax, isDegrees=False, curve_type='LINEAR', source_space='LOCAL_SPACE'):
    """Create a driver combining several sources (slots) into one target.

    slots: list of dicts, each with 'from_path' and 'source_name' (the same
    shape single-source driver creation already resolves) describing one
    variable's source.
    combine_mode: one of MULTI_SOURCE_COMBINE_MODES.
    fromMin/fromMax describe the expected range of the COMBINED value (set
    by the user, since combining sources changes the effective range).
    """
    print(f"=== MULTI-SOURCE DRIVER CREATION START ===")
    print(f"SLOTS: {len(slots)}  COMBINE: {combine_mode}")
    print(f"TO: {to_path}")
    print(f"COMBINED FROM RANGE: {fromMin} to {fromMax}")
    print(f"TO RANGE: {toMin} to {toMax}")
    print(f"CURVE TYPE: {curve_type}")

    if isDegrees:
        toMin = math.radians(toMin)
        toMax = math.radians(toMax)
    toMax = toMax + 0.0001

    original_fromMin, original_fromMax = fromMin, fromMax
    original_toMin, original_toMax = toMin, toMax

    if fromMin > fromMax:
        fromMin, fromMax = fromMax, fromMin

    try:
        target_data_block, target_data_path, to_index = parse_target_path(to_path)
        if not target_data_block:
            print("ERROR: Failed to parse target path")
            return False

        slot_source_configs = []
        for i, slot in enumerate(slots):
            cfg = parse_source_path(slot['from_path'], slot['source_name'])
            if not cfg:
                print(f"ERROR: Failed to parse source path for slot {i}: {slot.get('from_path')}")
                return False
            if cfg.get('type') in ('bone', 'object'):
                cfg['space'] = source_space
            slot_source_configs.append(cfg)

        remove_existing_driver(target_data_block, target_data_path, to_index)
        fcurve = add_new_driver(target_data_block, target_data_path, to_index)
        if not fcurve:
            print("ERROR: Failed to add driver")
            return False

        combine_expr = configure_multi_source_driver(fcurve, slot_source_configs, combine_mode)
        if not combine_expr:
            print("ERROR: Failed to configure multi-source driver")
            return False

        expression = create_mapping_expression(
            original_fromMin, original_fromMax, original_toMin, original_toMax,
            curve_type, drv_expr=combine_expr
        )
        if not expression:
            print("ERROR: Failed to create expression")
            return False

        fcurve.driver.expression = expression + f"  # {EASYDRIVER_MARKER}:{curve_type.upper()}:MULTI_{combine_mode.upper()}"
        print(f"✓ Expression: {expression}")

        bpy.context.view_layer.update()
        print(f"✓ SUCCESS: Multi-source driver created!")
        return True

    except Exception as e:
        print(f"ERROR: Exception in createMultiSourceDriver: {e}")
        import traceback
        traceback.print_exc()
        return False

def remove_existing_driver(data_block, data_path, index):
    """Remove existing driver if present."""
    try:
        if index == -1:
            data_block.driver_remove(data_path)
        else:
            data_block.driver_remove(data_path, index)
        print("✓ Old driver removed")
    except:
        print("✓ No old driver to remove")

def add_new_driver(data_block, data_path, index):
    """Add new driver and return fcurve."""
    try:
        if index == -1:
            fcurve = data_block.driver_add(data_path)
        else:
            fcurve = data_block.driver_add(data_path, index)
        
        if fcurve is None:
            print("ERROR: driver_add returned None")
            return None
        
        print(f"✓ Driver added: {fcurve}")
        return fcurve
    except Exception as e:
        print(f"ERROR: Failed to add driver: {e}")
        return None

def _configure_variable(var, source_config):
    """Configure a single driver variable from a source_config dict.

    Shared by configure_driver (single source, variable named 'drv') and
    configure_multi_source_driver (multiple sources, named v0, v1, ...).
    """
    try:
        space = source_config.get('space', 'LOCAL_SPACE')

        if source_config['type'] == 'bone':
            print("✓ Configuring bone source...")
            var.type = 'TRANSFORMS'
            target = var.targets[0]

            target.id = source_config['armature']
            target.bone_target = source_config['bone_name']

            prop = source_config['property']
            index = source_config['index']

            transform_map = {
                ('location', 0): 'LOC_X',
                ('location', 1): 'LOC_Y',
                ('location', 2): 'LOC_Z',
                ('rotation_euler', 0): 'ROT_X',
                ('rotation_euler', 1): 'ROT_Y',
                ('rotation_euler', 2): 'ROT_Z',
                ('scale', 0): 'SCALE_X',
                ('scale', 1): 'SCALE_Y',
                ('scale', 2): 'SCALE_Z'
            }

            if (prop, index) in transform_map:
                target.transform_type = transform_map[(prop, index)]
            else:
                print(f"ERROR: Unsupported transform type: {prop}[{index}]")
                return False

            target.transform_space = space

        elif source_config['type'] == 'object':
            if space == 'WORLD_SPACE':
                # World-space object transforms need a TRANSFORMS variable
                # (not SINGLE_PROP, which can only read the object's own
                # local transform channels) with no bone_target set.
                print("✓ Configuring object source (world space)...")
                var.type = 'TRANSFORMS'
                target = var.targets[0]
                target.id = source_config['object']
                target.bone_target = ""

                prop = source_config['property']
                index = source_config['index']
                transform_map = {
                    ('location', 0): 'LOC_X', ('location', 1): 'LOC_Y', ('location', 2): 'LOC_Z',
                    ('rotation_euler', 0): 'ROT_X', ('rotation_euler', 1): 'ROT_Y', ('rotation_euler', 2): 'ROT_Z',
                    ('scale', 0): 'SCALE_X', ('scale', 1): 'SCALE_Y', ('scale', 2): 'SCALE_Z'
                }
                if (prop, index) in transform_map:
                    target.transform_type = transform_map[(prop, index)]
                else:
                    print(f"ERROR: Unsupported transform type: {prop}[{index}]")
                    return False
                target.transform_space = 'WORLD_SPACE'
            else:
                print("✓ Configuring object source (local space)...")
                var.type = 'SINGLE_PROP'
                target = var.targets[0]
                target.id = source_config['object']
                target.data_path = f"{source_config['property']}[{source_config['index']}]"

        elif source_config['type'] == 'custom_prop':
            print("✓ Configuring custom property source...")
            var.type = 'SINGLE_PROP'
            target = var.targets[0]
            target.id_type = 'OBJECT'
            target.id = source_config['object']
            target.data_path = source_config['data_path']

        elif source_config['type'] == 'shapekey_source':
            print("✓ Configuring shape key source...")
            var.type = 'SINGLE_PROP'
            target = var.targets[0]
            target.id_type = 'KEY'
            target.id = source_config['object'].data.shape_keys
            target.data_path = f'key_blocks["{source_config["key_name"]}"].value'

        elif source_config['type'] == 'custom_path':
            print("✓ Configuring custom path source...")
            var.type = 'SINGLE_PROP'
            target = var.targets[0]
            target.id_type = source_config['id_type']
            target.id = source_config['id_block']
            target.data_path = source_config['data_path']

        else:
            print(f"ERROR: Unknown source type: {source_config['type']}")
            return False

        print(f"✓ Variable configured: {var.name} ({var.type})")
        return True

    except Exception as e:
        print(f"ERROR: Failed to configure variable: {e}")
        return False


def configure_driver(fcurve, source_config):
    """Configure the driver with a single source variable named 'drv'."""
    try:
        driver = fcurve.driver
        driver.type = 'SCRIPTED'

        # Clear existing variables
        while len(driver.variables) > 0:
            driver.variables.remove(driver.variables[0])

        # Add variable
        var = driver.variables.new()
        var.name = "drv"

        return _configure_variable(var, source_config)

    except Exception as e:
        print(f"ERROR: Failed to configure driver: {e}")
        return False


# Combine modes for multi-source drivers
MULTI_SOURCE_COMBINE_MODES = ('ADD', 'MULTIPLY', 'SUBTRACT', 'DISTANCE')


def build_multi_source_combine_expr(count, combine_mode):
    """Build the expression string combining v0..v(count-1) per the chosen mode."""
    names = [f"v{i}" for i in range(count)]
    combine_mode = (combine_mode or 'ADD').upper()

    if combine_mode == 'DISTANCE':
        if count != 2:
            return None, "Distance mode needs exactly 2 sources"
        return f"(abs(v0-v1))", None

    if combine_mode == 'ADD':
        return f"({'+'.join(names)})", None
    elif combine_mode == 'MULTIPLY':
        return f"({'*'.join(names)})", None
    elif combine_mode == 'SUBTRACT':
        return f"({'-'.join(names)})", None

    return None, f"Unknown combine mode: {combine_mode}"


def configure_multi_source_driver(fcurve, slot_source_configs, combine_mode):
    """Configure the driver with multiple source variables (v0, v1, ...) combined
    per combine_mode. Returns the combine expression string, or None on failure."""
    try:
        driver = fcurve.driver
        driver.type = 'SCRIPTED'

        while len(driver.variables) > 0:
            driver.variables.remove(driver.variables[0])

        for i, source_config in enumerate(slot_source_configs):
            var = driver.variables.new()
            var.name = f"v{i}"
            if not _configure_variable(var, source_config):
                print(f"ERROR: Failed to configure multi-source variable v{i}")
                return None

        combine_expr, err = build_multi_source_combine_expr(len(slot_source_configs), combine_mode)
        if err:
            print(f"ERROR: {err}")
            return None

        return combine_expr

    except Exception as e:
        print(f"ERROR: Failed to configure multi-source driver: {e}")
        return None

def create_mapping_expression(fromMin, fromMax, toMin, toMax, curve_type='LINEAR', drv_expr='drv'):
    """Create the source->target mapping expression for the given curve type.

    drv_expr is the raw input value expression - normally just the driver
    variable name "drv", but for multi-source drivers this is instead the
    combined expression (e.g. "(v0+v1)") built from several variables.

    All curve types share the same normalized parameter:
        t = (input - fromMin) / (fromMax - fromMin)
    which is 0 at fromMin and 1 at fromMax, and handles a reversed
    (fromMin > fromMax) range correctly because the sign flip in the
    denominator cancels the sign flip in the numerator.

    LINEAR   : input is clamped to the source range, t maps straight to output.
    BEZIER   : input is clamped to the source range, t is smoothstepped
               (3t^2 - 2t^3) before mapping - a symmetric ease-in/ease-out.
    EASE_IN  : input is clamped; t is squared (t^2) - starts slow, accelerates
               into the target value.
    EASE_OUT : input is clamped; t uses 1-(1-t)^2 - starts fast, decelerates
               into the target value.
    STEP     : input is clamped; output snaps straight to Min or Max at the
               halfway point of the source range - no in-between values.
    LOOPING  : input is wrapped (modulo) into the source range instead of
               clamped, so the output repeats (sawtooth) as input keeps
               increasing or decreasing past the range.
    PINGPONG : like LOOPING, but bounces back and forth (triangle wave)
               between Min and Max instead of snapping back to Min at the
               end of each cycle.
    INFINITE : input is NOT clamped or wrapped - output extrapolates
               linearly beyond [toMin, toMax] when input goes beyond
               [fromMin, fromMax].
    """

    # Check for division by zero
    range_diff = fromMax - fromMin
    if abs(range_diff) < 0.000001:
        print(f"ERROR: Source range too small: {range_diff}")
        return None

    clamp_min = min(fromMin, fromMax)
    clamp_max = max(fromMin, fromMax)
    range_abs = clamp_max - clamp_min  # always > 0, checked above

    curve_type = (curve_type or 'LINEAR').upper()
    drv = f"({drv_expr})"

    if curve_type == 'INFINITE':
        # No clamping at all - raw linear extrapolation.
        input_expr = drv

    elif curve_type == 'LOOPING':
        # Wrap drv into [clamp_min, clamp_max) using modulo. Python's %
        # always returns a result with the same sign as the (positive)
        # divisor here, so this stays in range for both directions.
        input_expr = f"(({clamp_min}) + (({drv} - ({clamp_min})) % ({range_abs})))"

    elif curve_type == 'PINGPONG':
        # Triangle wave: fold the sawtooth back on itself every half-period
        # so the value bounces clamp_min -> clamp_max -> clamp_min -> ...
        # instead of snapping back to clamp_min at the end of each cycle.
        period = range_abs * 2
        pos_expr = f"(({drv} - ({clamp_min})) % ({period}))"
        triangle_expr = f"(({range_abs}) - abs(({pos_expr}) - ({range_abs})))"
        input_expr = f"(({clamp_min}) + ({triangle_expr}))"

    else:
        # LINEAR, BEZIER, EASE_IN, EASE_OUT, and STEP all clamp the input.
        input_expr = f"max({clamp_min}, min({clamp_max}, {drv}))"

    # Normalized 0..1 (or slightly beyond, for INFINITE) parameter.
    t_expr = f"((({input_expr}) - ({fromMin})) / (({fromMax}) - ({fromMin})))"

    if curve_type == 'BEZIER':
        # Smoothstep ease: s = t^2 * (3 - 2t). At t=0 -> 0, at t=1 -> 1,
        # monotonic and symmetric in between (derivative 6t(1-t) >= 0 for t in [0,1]).
        #
        # IMPORTANT: Blender's driver.expression field has a hard 256-character
        # limit - if you go over it, Blender silently truncates the string,
        # which produces a broken/garbled expression with no error shown.
        # Writing t_expr out three times (once per use in t*t*(3-2*t)) blows
        # past that limit for real-world values like radians. Instead we
        # compute t exactly once using a Python assignment expression
        # (walrus operator) and reuse the short name "t" - this is valid
        # inside a driver expression since it's still a single expression,
        # just far shorter.
        eased_expr = f"((t:=({t_expr}))*t*(3-2*t))"
        expression = f"(({toMin}) + ({eased_expr}) * (({toMax}) - ({toMin})))"

    elif curve_type == 'EASE_IN':
        # s = t^2. At t=0 -> 0, t=1 -> 1, monotonic (derivative 2t >= 0 on [0,1]).
        # Same walrus trick as Bezier to keep the expression short.
        eased_expr = f"((t:=({t_expr}))*t)"
        expression = f"(({toMin}) + ({eased_expr}) * (({toMax}) - ({toMin})))"

    elif curve_type == 'EASE_OUT':
        # s = 1-(1-t)^2 = 2t - t^2. At t=0 -> 0, t=1 -> 1, monotonic
        # (derivative 2-2t >= 0 on [0,1]).
        eased_expr = f"((t:=({t_expr}))*(2-t))"
        expression = f"(({toMin}) + ({eased_expr}) * (({toMax}) - ({toMin})))"

    elif curve_type == 'STEP':
        # Binary snap at the halfway point of the source range - no
        # in-between values, just Min or Max.
        stepped_expr = f"(1 if ({t_expr})>=0.5 else 0)"
        expression = f"(({toMin}) + ({stepped_expr}) * (({toMax}) - ({toMin})))"

    else:
        # LINEAR, LOOPING, and INFINITE all map t straight through -
        # they only differ in how the input was prepared above.
        expression = f"(({toMin}) + ({t_expr}) * (({toMax}) - ({toMin})))"

    return expression


#---------------------------------------
# Updating Fine tune values - BONES
#---------------------------------------
def update_fine_tune_min_value(self, context):
    """Update bone min value when fine tune input changes."""
    props = context.scene.driver_recorder_props
    axis = props.fine_tune_axis
    value = props.fine_tune_min_value
    
    if axis in ["LOC_X", "LOC_Y", "LOC_Z"]:
        axis_idx = ["LOC_X", "LOC_Y", "LOC_Z"].index(axis)
        loc = list(props.from_min_location)
        loc[axis_idx] = value
        props.from_min_location = loc
    elif axis in ["ROT_X", "ROT_Y", "ROT_Z"]:
        axis_idx = ["ROT_X", "ROT_Y", "ROT_Z"].index(axis)
        rot = list(props.from_min_rotation)
        rot[axis_idx] = value
        props.from_min_rotation = rot
    elif axis in ["SCALE_X", "SCALE_Y", "SCALE_Z"]:
        axis_idx = ["SCALE_X", "SCALE_Y", "SCALE_Z"].index(axis)
        scale = list(props.from_min_scale)
        scale[axis_idx] = value
        props.from_min_scale = scale

def update_fine_tune_max_value(self, context):
    """Update bone max value when fine tune input changes."""
    props = context.scene.driver_recorder_props
    axis = props.fine_tune_axis
    value = props.fine_tune_max_value
    
    if axis in ["LOC_X", "LOC_Y", "LOC_Z"]:
        axis_idx = ["LOC_X", "LOC_Y", "LOC_Z"].index(axis)
        loc = list(props.from_max_location)
        loc[axis_idx] = value
        props.from_max_location = loc
    elif axis in ["ROT_X", "ROT_Y", "ROT_Z"]:
        axis_idx = ["ROT_X", "ROT_Y", "ROT_Z"].index(axis)
        rot = list(props.from_max_rotation)
        rot[axis_idx] = value
        props.from_max_rotation = rot
    elif axis in ["SCALE_X", "SCALE_Y", "SCALE_Z"]:
        axis_idx = ["SCALE_X", "SCALE_Y", "SCALE_Z"].index(axis)
        scale = list(props.from_max_scale)
        scale[axis_idx] = value
        props.from_max_scale = scale

def update_fine_tune_axis(self, context):
    """Update axis and sync values when axis changes."""
    props = context.scene.driver_recorder_props
    axis = props.fine_tune_axis
    
    # Update detected axis display
    axis_display_map = {
        "LOC_X": "LOC X", "LOC_Y": "LOC Y", "LOC_Z": "LOC Z",
        "ROT_X": "ROT X", "ROT_Y": "ROT Y", "ROT_Z": "ROT Z"
    }
    props.from_detected_axis = axis_display_map.get(axis, "LOC X")
    
    # Update fine tune values to match new axis
    if axis in ["LOC_X", "LOC_Y", "LOC_Z"]:
        axis_idx = ["LOC_X", "LOC_Y", "LOC_Z"].index(axis)
        props.fine_tune_min_value = props.from_min_location[axis_idx]
        props.fine_tune_max_value = props.from_max_location[axis_idx]
    elif axis in ["ROT_X", "ROT_Y", "ROT_Z"]:
        axis_idx = ["ROT_X", "ROT_Y", "ROT_Z"].index(axis)
        props.fine_tune_min_value = props.from_min_rotation[axis_idx]
        props.fine_tune_max_value = props.from_max_rotation[axis_idx]
    elif axis in ["SCALE_X", "SCALE_Y", "SCALE_Z"]:
        axis_idx = ["SCALE_X", "SCALE_Y", "SCALE_Z"].index(axis)
        props.fine_tune_min_value = props.from_min_scale[axis_idx]
        props.fine_tune_max_value = props.from_max_scale[axis_idx]

#---------------------------------------
# Updating Fine tune values - Objects
#---------------------------------------
def update_fine_tune_object_min_value(self, context):
    """Update object min value when fine tune input changes."""
    props = context.scene.driver_recorder_props
    axis = props.fine_tune_object_axis
    value = props.fine_tune_object_min_value
    
    if axis in ["LOC_X", "LOC_Y", "LOC_Z"]:
        axis_idx = ["LOC_X", "LOC_Y", "LOC_Z"].index(axis)
        loc = list(props.from_object_min_location)
        loc[axis_idx] = value
        props.from_object_min_location = loc
    elif axis in ["ROT_X", "ROT_Y", "ROT_Z"]:
        axis_idx = ["ROT_X", "ROT_Y", "ROT_Z"].index(axis)
        rot = list(props.from_object_min_rotation)
        rot[axis_idx] = value
        props.from_object_min_rotation = rot
    elif axis in ["SCALE_X", "SCALE_Y", "SCALE_Z"]:
        axis_idx = ["SCALE_X", "SCALE_Y", "SCALE_Z"].index(axis)
        scale = list(props.from_object_min_scale)
        scale[axis_idx] = value
        props.from_object_min_scale = scale

def update_fine_tune_object_max_value(self, context):
    """Update object max value when fine tune input changes."""
    props = context.scene.driver_recorder_props
    axis = props.fine_tune_object_axis
    value = props.fine_tune_object_max_value
    
    if axis in ["LOC_X", "LOC_Y", "LOC_Z"]:
        axis_idx = ["LOC_X", "LOC_Y", "LOC_Z"].index(axis)
        loc = list(props.from_object_max_location)
        loc[axis_idx] = value
        props.from_object_max_location = loc
    elif axis in ["ROT_X", "ROT_Y", "ROT_Z"]:
        axis_idx = ["ROT_X", "ROT_Y", "ROT_Z"].index(axis)
        rot = list(props.from_object_max_rotation)
        rot[axis_idx] = value
        props.from_object_max_rotation = rot
    elif axis in ["SCALE_X", "SCALE_Y", "SCALE_Z"]:
        axis_idx = ["SCALE_X", "SCALE_Y", "SCALE_Z"].index(axis)
        scale = list(props.from_object_max_scale)
        scale[axis_idx] = value
        props.from_object_max_scale = scale

def update_fine_tune_object_axis(self, context):
    """Update object axis and sync values when axis changes."""
    props = context.scene.driver_recorder_props
    axis = props.fine_tune_object_axis
    
    # Update detected axis display
    axis_display_map = {
        "LOC_X": "LOC X", "LOC_Y": "LOC Y", "LOC_Z": "LOC Z",
        "ROT_X": "ROT X", "ROT_Y": "ROT Y", "ROT_Z": "ROT Z",
        "SCALE_X": "SCALE X", "SCALE_Y": "SCALE Y", "SCALE_Z": "SCALE Z"
    }
    props.from_object_detected_axis = axis_display_map.get(axis, "LOC X")
    
    # Update fine tune values to match new axis
    if axis in ["LOC_X", "LOC_Y", "LOC_Z"]:
        axis_idx = ["LOC_X", "LOC_Y", "LOC_Z"].index(axis)
        props.fine_tune_object_min_value = props.from_object_min_location[axis_idx]
        props.fine_tune_object_max_value = props.from_object_max_location[axis_idx]
    elif axis in ["ROT_X", "ROT_Y", "ROT_Z"]:
        axis_idx = ["ROT_X", "ROT_Y", "ROT_Z"].index(axis)
        props.fine_tune_object_min_value = props.from_object_min_rotation[axis_idx]
        props.fine_tune_object_max_value = props.from_object_max_rotation[axis_idx]
    elif axis in ["SCALE_X", "SCALE_Y", "SCALE_Z"]:
        axis_idx = ["SCALE_X", "SCALE_Y", "SCALE_Z"].index(axis)
        props.fine_tune_object_min_value = props.from_object_min_scale[axis_idx]
        props.fine_tune_object_max_value = props.from_object_max_scale[axis_idx]


def auto_apply_armature_source(self, context):
    """Auto-apply armature source when selection changes."""
    props = context.scene.driver_recorder_props
    
    if props.manual_source_armature:
        # Clear object source when armature is selected
        props.manual_source_object = None
        
        # If we have a bone selected, apply immediately
        if props.manual_source_bone:
            apply_bone_source_internal(props, props.manual_source_armature, props.manual_source_bone)


def auto_apply_bone_source(self, context):
    """Auto-apply bone source when bone selection changes."""
    props = context.scene.driver_recorder_props
    
    if props.manual_source_armature and props.manual_source_bone:
        apply_bone_source_internal(props, props.manual_source_armature, props.manual_source_bone)

def auto_apply_object_source(self, context):
    """Auto-apply object source when selection changes."""
    props = context.scene.driver_recorder_props
    
    if props.manual_source_object:
        # Clear bone source when object is selected
        props.manual_source_armature = None
        props.manual_source_bone = ""
        
        apply_object_source_internal(props, props.manual_source_object)

def apply_bone_source_internal(props, armature, bone_name):
    """Internal function to apply bone source while preserving recorded min/max data."""
    # Validate bone exists
    if bone_name not in armature.pose.bones:
        print(f"ERROR: Bone '{bone_name}' not found in armature '{armature.name}'")
        return False
    
    # Clear object source data (switching to bone mode)
    props.from_object = ""
    props.from_object_has_min = False
    props.from_object_has_max = False
    props.from_object_detected_axis = ""
    
    # Update bone source (PRESERVE min/max flags and detected axis!)
    props.from_armature = armature.name
    props.from_bone = bone_name
    
    # Don't clear the has_min, has_max, or detected_axis flags
    # The recorded min/max values stay the same, only the source bone changes
    
    print(f"Fine-tune applied bone source: {armature.name} > {bone_name}")
    print(f"  Preserved: has_min={props.from_has_min}, has_max={props.from_has_max}, axis={props.from_detected_axis}")
    return True

def apply_object_source_internal(props, obj):
    """Internal function to apply object source while preserving recorded min/max data."""
    # Clear bone source data (switching to object mode)
    props.from_armature = ""
    props.from_bone = ""
    props.from_has_min = False
    props.from_has_max = False
    props.from_detected_axis = ""
    
    # Update object source (PRESERVE min/max flags and detected axis!)
    props.from_object = obj.name
    
    # Don't clear the has_min, has_max, or detected_axis flags
    # The recorded min/max values stay the same, only the source object changes
    
    print(f"Fine-tune applied object source: {obj.name}")
    print(f"  Preserved: has_min={props.from_object_has_min}, has_max={props.from_object_has_max}, axis={props.from_object_detected_axis}")
    return True



#---------------------------------------
# Utilities
#---------------------------------------




def extract_array_index(data_path):
    """Extract array index from data path if present."""
    array_match = re.search(r'(.+)\[(\d+)\]$', data_path)
    if array_match:
        return array_match.group(1), int(array_match.group(2))
    return data_path, -1

def auto_detect_path_type(data_block, data_path, index=-1):
    """Safely detect property type using Blender's path resolution."""
    try:
        if data_block is None or data_path is None:
            return 'FLOAT'  # Default fallback
        
        print(f"DEBUG: Resolving path '{data_path}' on {type(data_block).__name__}")
        
        if index >= 0:
            # Array property
            prop_value = data_block.path_resolve(data_path)[index]
        else:
            # Single property
            prop_value = data_block.path_resolve(data_path)
            
        if isinstance(prop_value, bool):
            return 'BOOLEAN'
        elif isinstance(prop_value, (int, float)):
            return 'FLOAT'
        else:
            return 'FLOAT'  # Default fallback      
    except Exception as e:
        print(f"Path resolution failed on {type(data_block).__name__}: {e}")
        print(f"  Data path: '{data_path}'")
        print(f"  Index: {index}")
        return 'FLOAT'




def parse_target_path(to_path):
    """Parse the target path and return data block, data path, and index."""
    
    print(f"DEBUG: Parsing path: {to_path}")
    
    # Pattern definitions with their handlers
    patterns = [
        # Long format patterns (bpy.data...)
        (r'bpy\.data\.materials\["([^"]+)"\]\.node_tree\.nodes\["([^"]+)"\]\.color_ramp\.elements\[(\d+)\]\.(.+)', 
         'colorramp_long', "✓ COLORRAMP ELEMENT (LONG FORMAT) DETECTED!"),
        
        (r'bpy\.data\.materials\["([^"]+)"\]\.node_tree\.nodes\["([^"]+)"\]\.(inputs|outputs)\[(\d+)\]\.default_value', 
         'material_node_long', "✓ MATERIAL NODE (LONG FORMAT) DETECTED!"),
        
        (r'bpy\.data\.objects\["([^"]+)"\]\.constraints\["([^"]+)"\]\.(.+)', 
         'constraint_long', "✓ OBJECT CONSTRAINT (LONG FORMAT) DETECTED!"),
        
        (r'bpy\.data\.objects\["([^"]+)"\]\.data\.shape_keys\.key_blocks\["([^"]+)"\]\.value', 
         'shapekey_long', "✓ SHAPEKEY (LONG FORMAT) DETECTED!"),
        
        (r'bpy\.data\.objects\["([^"]+)"\]\.pose\.bones\["([^"]+)"\]\.([a-zA-Z_]+)(?:\[(\d+)\])?', 
         'bone_long', "✓ BONE TRANSFORM (LONG FORMAT) DETECTED!"),
        
        # Custom properties pattern (must be before general object pattern)
        (r'bpy\.data\.objects\["([^"]+)"\]\["([^"]+)"\]', 
         'object_custom_prop_long', "✓ OBJECT CUSTOM PROPERTY (LONG FORMAT) DETECTED!"),
        
        (r'bpy\.data\.cameras\["([^"]+)"\]\.(.+)', 
         'camera_long', "✓ CAMERA PROPERTY (LONG FORMAT) DETECTED!"),
        
        (r'bpy\.data\.lights\["([^"]+)"\]\.(.+)', 
         'light_long', "✓ LIGHT PROPERTY (LONG FORMAT) DETECTED!"),
        
        (r'bpy\.data\.materials\["([^"]+)"\]\.(.+)', 
         'material_long', "✓ GENERAL MATERIAL PROPERTY (LONG FORMAT) DETECTED!"),
        
        (r'bpy\.data\.armatures\["([^"]+)"\]\.(.+)', 
         'armature_long', "✓ ARMATURE PROPERTY (LONG FORMAT) DETECTED!"),
        
        (r'bpy\.data\.objects\["([^"]+)"\]\.(.+)', 
         'object_long', "✓ GENERAL OBJECT PROPERTY (LONG FORMAT) DETECTED!"),
        
        # Short format patterns (only if not starting with bpy.data.)
        (r'(.+)\.data\.shape_keys\.key_blocks\["([^"]+)"\]\.value', 
         'shapekey_short', "✓ SHAPEKEY (SHORT FORMAT) DETECTED!"),
        
        (r'(.+)\.pose\.bones\["([^"]+)"\]\.([a-zA-Z_]+)(?:\[(\d+)\])?', 
         'bone_short', "✓ BONE TRANSFORM (SHORT FORMAT) DETECTED!"),
        
        (r'(.+)\.constraints\["([^"]+)"\]\.(.+)', 
         'constraint_short', "✓ OBJECT CONSTRAINT (SHORT FORMAT) DETECTED!"),
        
        (r'(.+)\.node_tree\.nodes\["([^"]+)"\]\.(inputs|outputs)\[(\d+)\]\.default_value', 
         'material_node_short', "✓ MATERIAL NODE (SHORT FORMAT) DETECTED!"),
        
        # Custom properties pattern (short format - must be before general pattern)
        (r'(.+)\["([^"]+)"\]$', 
         'custom_prop_short', "✓ CUSTOM PROPERTY (SHORT FORMAT) DETECTED!"),
        
        (r'(.+)\.(.+)', 
         'general_short', "✓ GENERAL PROPERTY (SHORT FORMAT) DETECTED!"),
    ]
    
    def get_data_block(name, data_type):
        """Get data block by name and type with error checking."""
        collections = {
            'objects': bpy.data.objects,
            'materials': bpy.data.materials,
            'armatures': bpy.data.armatures,
            'cameras': bpy.data.cameras,
            'lights': bpy.data.lights
        }
        
        if name not in collections[data_type]:
            print(f"ERROR: {data_type.capitalize()[:-1]} '{name}' not found!")
            print(f"Available {data_type}: {list(collections[data_type].keys())}")
            return None
        return collections[data_type][name]
    
    def validate_node_tree(material, node_name):
        """Validate material node tree and node existence."""
        if not material.node_tree:
            print(f"ERROR: Material '{material.name}' has no node tree!")
            return None
        if node_name not in material.node_tree.nodes:
            print(f"ERROR: Node '{node_name}' not found!")
            return None
        return material.node_tree.nodes[node_name]
    
    # Pattern handlers
    def handle_colorramp_long(groups):
        material_name, node_name, element_index, property_name = groups
        element_index = int(element_index)
        
        material = get_data_block(material_name, 'materials')
        if not material: return None, None, None
        
        node = validate_node_tree(material, node_name)
        if not node: return None, None, None
        
        if not hasattr(node, 'color_ramp') or element_index >= len(node.color_ramp.elements):
            print(f"ERROR: Invalid ColorRamp node or element index!")
            return None, None, None
        
        relative_path = f'nodes["{node_name}"].color_ramp.elements[{element_index}].{property_name}'
        data_path, index = extract_array_index(relative_path)
        return material.node_tree, data_path, index
    
    def handle_material_node_long(groups):
        # groups: (material_name, node_name, socket_type, socket_index)
        # socket_type is now explicitly captured from the regex ("inputs" or "outputs")
        material_name, node_name, socket_type, socket_index = groups
        socket_index = int(socket_index)

        material = get_data_block(material_name, 'materials')
        if not material: return None, None, None

        node = validate_node_tree(material, node_name)
        if not node: return None, None, None

        # Validate socket type and index (compatible with Blender 4.0–5.x)
        node_sockets = getattr(node, socket_type, None)
        if node_sockets is None:
            print(f"ERROR: Node has no '{socket_type}' attribute!")
            return None, None, None
        if socket_index >= len(node_sockets):
            print(f"ERROR: {socket_type.capitalize()} index {socket_index} out of range (node has {len(node_sockets)})!")
            return None, None, None

        # Verify socket is driveable
        socket = node_sockets[socket_index]
        if not hasattr(socket, 'default_value'):
            print(f"ERROR: Socket has no default_value (may not be driveable)!")
            return None, None, None

        relative_path = f'nodes["{node_name}"].{socket_type}[{socket_index}].default_value'
        return material.node_tree, relative_path, -1
    
    def handle_constraint_long(groups):
        obj_name, constraint_name, prop_path = groups
        obj = get_data_block(obj_name, 'objects')
        if not obj: return None, None, None
        
        if constraint_name not in obj.constraints:
            print(f"ERROR: Constraint '{constraint_name}' not found!")
            return None, None, None
        
        relative_path = f'constraints["{constraint_name}"].{prop_path}'
        data_path, index = extract_array_index(relative_path)
        return obj, data_path, index
    
    def handle_shapekey_long(groups):
        obj_name, shapekey_name = groups
        obj = get_data_block(obj_name, 'objects')
        if not obj: return None, None, None
        
        if not obj.data or not hasattr(obj.data, 'shape_keys') or not obj.data.shape_keys:
            print(f"ERROR: Object has no shape keys!")
            return None, None, None
        
        relative_path = f'key_blocks["{shapekey_name}"].value'
        return obj.data.shape_keys, relative_path, -1
    
    def handle_bone_long(groups):
        obj_name, bone_name, prop_name, index_str = groups
        index = int(index_str) if index_str else -1
        
        obj = get_data_block(obj_name, 'objects')
        if not obj: return None, None, None
        
        if obj.type != 'ARMATURE' or not obj.pose or bone_name not in obj.pose.bones:
            print(f"ERROR: Invalid armature or bone!")
            return None, None, None
        
        relative_path = f'pose.bones["{bone_name}"].{prop_name}'
        return obj, relative_path, index
    
    def handle_object_custom_prop_long(groups):
        obj_name, prop_name = groups
        obj = get_data_block(obj_name, 'objects')
        if not obj: return None, None, None
        
        if prop_name not in obj:
            print(f"ERROR: Custom property '{prop_name}' not found on object '{obj_name}'!")
            available_props = list(obj.keys()) if obj.keys() else []
            print(f"Available custom properties: {available_props}")
            return None, None, None
        
        relative_path = f'["{prop_name}"]'
        return obj, relative_path, -1
    
    def handle_camera_long(groups):
        camera_name, prop_path = groups
        camera = get_data_block(camera_name, 'cameras')
        if not camera: return None, None, None
        
        data_path, index = extract_array_index(prop_path)
        return camera, data_path, index
    
    def handle_light_long(groups):
        light_name, prop_path = groups
        light = get_data_block(light_name, 'lights')
        if not light: return None, None, None
        
        data_path, index = extract_array_index(prop_path)
        return light, data_path, index
    
    def handle_material_long(groups):
        material_name, prop_path = groups
        material = get_data_block(material_name, 'materials')
        if not material: return None, None, None
        
        data_path, index = extract_array_index(prop_path)
        return material, data_path, index
    
    def handle_armature_long(groups):
        armature_name, prop_path = groups
        armature = get_data_block(armature_name, 'armatures')
        if not armature: return None, None, None
        
        data_path, index = extract_array_index(prop_path)
        return armature, data_path, index
    
    def handle_object_long(groups):
        obj_name, prop_path = groups
        obj = get_data_block(obj_name, 'objects')
        if not obj: return None, None, None
        
        data_path, index = extract_array_index(prop_path)
        return obj, data_path, index
    
    def handle_custom_prop_short(groups):
        name, prop_name = groups
        
        # Try different data types for custom properties
        for data_type in ['objects', 'materials', 'armatures', 'cameras', 'lights']:
            if name in getattr(bpy.data, data_type):
                data_block = getattr(bpy.data, data_type)[name]
                if prop_name in data_block:
                    relative_path = f'["{prop_name}"]'
                    return data_block, relative_path, -1
                else:
                    print(f"ERROR: Custom property '{prop_name}' not found!")
                    return None, None, None
        
        print(f"ERROR: '{name}' not found in any data collection!")
        return None, None, None
    
    def handle_general_short(groups):
        name, prop_path = groups
        
        # Try different data types
        for data_type in ['objects', 'materials', 'armatures', 'cameras', 'lights']:
            if name in getattr(bpy.data, data_type):
                data_block = getattr(bpy.data, data_type)[name]
                data_path, index = extract_array_index(prop_path)
                return data_block, data_path, index
        
        print(f"ERROR: '{name}' not found in any data collection!")
        return None, None, None
    
    # Handler mapping
    handlers = {
        'colorramp_long': handle_colorramp_long,
        'material_node_long': handle_material_node_long,
        'constraint_long': handle_constraint_long,
        'shapekey_long': handle_shapekey_long,
        'bone_long': handle_bone_long,
        'object_custom_prop_long': handle_object_custom_prop_long,
        'camera_long': handle_camera_long,
        'light_long': handle_light_long,
        'material_long': handle_material_long,
        'armature_long': handle_armature_long,
        'object_long': handle_object_long,
        'shapekey_short': handle_shapekey_long,  # Same logic
        'bone_short': handle_bone_long,  # Same logic
        'constraint_short': handle_constraint_long,  # Same logic
        'material_node_short': handle_material_node_long,  # Same logic
        'custom_prop_short': handle_custom_prop_short,
        'general_short': handle_general_short,
    }
    
    # Process patterns
    for pattern, handler_name, debug_msg in patterns:
        # Skip short format patterns if path starts with bpy.data.
        if not handler_name.endswith('_long') and to_path.startswith('bpy.data.'):
            continue
            
        match = re.match(pattern, to_path)
        if match:
            print(debug_msg)
            return handlers[handler_name](match.groups())
    
    # No pattern matched
    print(f"ERROR: Unsupported target path format: {to_path}")
    print("Supported formats:")
    print("  Short: OBJECT_NAME.property.path")
    print("  Long:  bpy.data.objects[\"OBJECT_NAME\"].property.path")
    print("  Custom: bpy.data.objects[\"OBJECT_NAME\"][\"custom_prop\"]")
    return None, None, None



def parse_source_path(from_path, armature_name):
    """Parse the source path and return configuration dict."""
    
    # Shape key value source: OBJECT_NAME.data.shape_keys.key_blocks["KEY"].value
    shapekey_src_match = re.match(r'(.+)\.data\.shape_keys\.key_blocks\["([^"]+)"\]\.value', from_path)
    if shapekey_src_match:
        print("✓ SHAPEKEY SOURCE DETECTED!")
        obj_name, key_name = shapekey_src_match.groups()
        if obj_name not in bpy.data.objects:
            print(f"ERROR: Source object '{obj_name}' not found!")
            return None
        obj = bpy.data.objects[obj_name]
        if not (obj.data and hasattr(obj.data, 'shape_keys') and obj.data.shape_keys):
            print(f"ERROR: Object '{obj_name}' has no shape keys!")
            return None
        if key_name not in obj.data.shape_keys.key_blocks:
            print(f"ERROR: Shape key '{key_name}' not found on '{obj_name}'!")
            return None
        return {
            'type': 'shapekey_source',
            'object': obj,
            'key_name': key_name,
        }

    # Bone transform source
    bone_match = re.match(r'(.+)\.pose\.bones\["([^"]+)"\]\.([a-zA-Z_]+)\[(\d+)\]', from_path)
    if bone_match:
        print("✓ BONE SOURCE DETECTED!")
        armature_path, bone_name, prop_name, index = bone_match.groups()
        index = int(index)
        
        if armature_name not in bpy.data.objects:
            print(f"ERROR: Source armature '{armature_name}' not found!")
            return None
        
        armature_obj = bpy.data.objects[armature_name]
        
        return {
            'type': 'bone',
            'armature': armature_obj,
            'bone_name': bone_name,
            'property': prop_name,
            'index': index
        }
    
    # Custom property on a bone: ARMATURE_NAME.pose.bones["BONE"]["PROP"]
    bone_custom_match = re.match(r'(.+)\.pose\.bones\["([^"]+)"\]\["([^"]+)"\]', from_path)
    if bone_custom_match:
        print("✓ BONE CUSTOM PROPERTY SOURCE DETECTED!")
        armature_name_path, bone_name, prop_name = bone_custom_match.groups()
        # armature_name_path may equal armature_name passed in, or the name extracted
        obj_name = armature_name_path
        if obj_name not in bpy.data.objects:
            print(f"ERROR: Armature '{obj_name}' not found!")
            return None
        obj = bpy.data.objects[obj_name]
        if obj.type != 'ARMATURE' or bone_name not in obj.pose.bones:
            print(f"ERROR: Bone '{bone_name}' not found in armature '{obj_name}'!")
            return None
        bone = obj.pose.bones[bone_name]
        if prop_name not in bone:
            print(f"ERROR: Custom property '{prop_name}' not found on bone '{bone_name}'!")
            return None
        data_path = f'pose.bones["{bone_name}"]["{prop_name}"]'
        return {
            'type': 'custom_prop',
            'object': obj,
            'data_path': data_path,
        }

    # Custom property on an object: OBJECT_NAME["PROP"]
    obj_custom_match = re.match(r'(.+)\["([^"]+)"\]$', from_path)
    if obj_custom_match:
        obj_name, prop_name = obj_custom_match.groups()
        if obj_name in bpy.data.objects and prop_name in bpy.data.objects[obj_name]:
            print("✓ OBJECT CUSTOM PROPERTY SOURCE DETECTED!")
            obj = bpy.data.objects[obj_name]
            data_path = f'["{prop_name}"]'
            return {
                'type': 'custom_prop',
                'object': obj,
                'data_path': data_path,
            }
        # This pattern's "object name" capture is greedy and can also match
        # complex nested paths (e.g. a node tree path ending in ["Name"])
        # that aren't actually simple object custom properties - fall
        # through to the general resolver instead of failing outright.

    # Object transform property source: OBJECT_NAME.location[0] etc.
    obj_match = re.match(r'(.+)\.([a-zA-Z_]+)\[(\d+)\]', from_path)
    if obj_match:
        obj_name, prop_name, index = obj_match.groups()
        index = int(index)

        if obj_name in bpy.data.objects:
            print("✓ OBJECT SOURCE DETECTED!")
            obj = bpy.data.objects[obj_name]
            return {
                'type': 'object',
                'object': obj,
                'property': prop_name,
                'index': index
            }
        # Same reasoning as above - this pattern's capture is greedy enough
        # to also match complex nested paths (node inputs, etc.) that aren't
        # simple object transforms. Fall through to the general resolver
        # instead of failing outright.
    
    print("INFO: No specific source pattern matched - trying general custom path resolution")
    custom_config = parse_custom_path_source(from_path)
    if custom_config:
        print("✓ CUSTOM PATH SOURCE DETECTED (general resolver)!")
        return custom_config

    print("ERROR: Invalid source path format")
    return None

def extract_array_index(data_path):
    """Extract array index from data path if present."""
    array_match = re.match(r'(.+)\[(\d+)\]$', data_path)
    if array_match:
        return array_match.group(1), int(array_match.group(2))
    return data_path, -1

def get_to_bones_data(props):
    """Get TO bones data from JSON string."""
    try:
        return json.loads(props.to_bones_data)
    except:
        return {}

def set_to_bones_data(props, data):
    """Set TO bones data as JSON string."""
    props.to_bones_data = json.dumps(data)

def get_shapekey_list_data(props):
    """Get shapekey list data from JSON string."""
    try:
        return json.loads(props.shapekey_list_data)
    except:
        return {}

def set_shapekey_list_data(props, data):
    """Set shapekey list data as JSON string."""
    props.shapekey_list_data = json.dumps(data)

def get_path_list_data(props):
    """Get path list data from JSON string."""
    try:
        return json.loads(props.path_list_data)
    except:
        return {}

def set_path_list_data(props, data):
    """Set path list data as JSON string."""
    props.path_list_data = json.dumps(data)


def resolve_active_single_source(props):
    """Resolve whichever single source is currently configured (bone/object
    transform, custom property, or shape key) into (from_path, from_min,
    from_max, source_name, error_message).

    On success error_message is None. On failure the first four values are
    None and error_message describes what's wrong - the caller reports it.

    This mirrors the priority-chain logic in ANIM_OT_create_drivers exactly,
    kept as a standalone function so the Multi-Source "Add Slot" operator can
    reuse the same resolution without touching that already-working operator.
    """
    if props.from_bone and props.from_has_min and props.from_has_max and props.from_detected_axis:
        armature = bpy.data.objects.get(props.from_armature)
        if not armature or props.from_bone not in armature.pose.bones:
            return None, None, None, None, f"Source bone '{props.from_bone}' not found in armature '{props.from_armature}'"

        from_axis_type, from_axis_name = props.from_detected_axis.split(' ')
        from_axis_index = ['X', 'Y', 'Z'].index(from_axis_name)

        if from_axis_type == 'LOC':
            from_min = props.from_min_location[from_axis_index]
            from_max = props.from_max_location[from_axis_index]
            from_prop = 'location'
        elif from_axis_type == 'ROT':
            from_min = props.from_min_rotation[from_axis_index]
            from_max = props.from_max_rotation[from_axis_index]
            from_prop = 'rotation_euler'
        elif from_axis_type == 'SCALE':
            from_min = props.from_min_scale[from_axis_index]
            from_max = props.from_max_scale[from_axis_index]
            from_prop = 'scale'
        else:
            return None, None, None, None, f"Unknown axis type '{from_axis_type}'"

        from_path = f'{props.from_armature}.pose.bones["{props.from_bone}"].{from_prop}[{from_axis_index}]'
        return from_path, from_min, from_max, props.from_armature, None

    elif props.from_object and props.from_object_has_min and props.from_object_has_max and props.from_object_detected_axis:
        obj = bpy.data.objects.get(props.from_object)
        if not obj:
            return None, None, None, None, f"Source object '{props.from_object}' not found"

        from_axis_type, from_axis_name = props.from_object_detected_axis.split(' ')
        from_axis_index = ['X', 'Y', 'Z'].index(from_axis_name)

        if from_axis_type == 'LOC':
            from_min = props.from_object_min_location[from_axis_index]
            from_max = props.from_object_max_location[from_axis_index]
            from_prop = 'location'
        elif from_axis_type == 'ROT':
            from_min = props.from_object_min_rotation[from_axis_index]
            from_max = props.from_object_max_rotation[from_axis_index]
            from_prop = 'rotation_euler'
        elif from_axis_type == 'SCALE':
            from_min = props.from_object_min_scale[from_axis_index]
            from_max = props.from_object_max_scale[from_axis_index]
            from_prop = 'scale'
        else:
            return None, None, None, None, f"Unknown axis type '{from_axis_type}'"

        from_path = f'{props.from_object}.{from_prop}[{from_axis_index}]'
        return from_path, from_min, from_max, props.from_object, None

    elif props.custom_prop_is_set and props.custom_prop_source_object:
        obj = props.custom_prop_source_object
        pname = props.custom_prop_name.strip()
        bname = props.custom_prop_bone.strip()
        from_min = props.custom_prop_min
        from_max = props.custom_prop_max

        if bname:
            if obj.type != 'ARMATURE' or bname not in obj.pose.bones:
                return None, None, None, None, f"Bone '{bname}' not found in armature '{obj.name}'"
            if pname not in obj.pose.bones[bname]:
                return None, None, None, None, f"Custom property '{pname}' not found on bone '{bname}'"
            from_path = f'{obj.name}.pose.bones["{bname}"]["{pname}"]'
        else:
            if pname not in obj:
                return None, None, None, None, f"Custom property '{pname}' not found on object '{obj.name}'"
            from_path = f'{obj.name}["{pname}"]'

        return from_path, from_min, from_max, obj.name, None

    elif props.shapekey_src_is_set and props.shapekey_src_object:
        obj = props.shapekey_src_object
        key_name = props.shapekey_src_name.strip()

        if not (obj.data and hasattr(obj.data, 'shape_keys') and obj.data.shape_keys):
            return None, None, None, None, f"'{obj.name}' has no shape keys"
        if key_name not in obj.data.shape_keys.key_blocks:
            return None, None, None, None, f"Shape key '{key_name}' not found on '{obj.name}'"

        from_min = props.shapekey_src_min
        from_max = props.shapekey_src_max
        from_path = f'{obj.name}.data.shape_keys.key_blocks["{key_name}"].value'
        return from_path, from_min, from_max, obj.name, None

    elif props.source_custom_path_is_set and props.source_custom_path_input:
        path_str = props.source_custom_path_input
        config = parse_custom_path_source(path_str)
        if not config:
            return None, None, None, None, f"Custom path '{path_str}' could not be resolved - it may have been deleted or renamed"

        from_min = props.source_path_min_value
        from_max = props.source_path_max_value
        source_name = config['id_block'].name
        return path_str, from_min, from_max, source_name, None

    return None, None, None, None, "No source configured. Please record MIN/MAX or set up a custom property/shape key source."



def ensure_euler_rotation(bone, override=False):
    """Return current rotation as Euler with optional permanent mode change.

    - If override=False: Return Euler values without permanently changing rotation_mode
      * Quaternion bones: temporarily convert to read Euler, then restore quaternion
      * Euler bones: keep as Euler and return values
    
    - If override=True: Force bone to XYZ Euler mode permanently
      * Clears keyframes/drivers on rotation_mode
      * Converts any rotation mode to XYZ Euler
      * Returns the Euler values
    """
    
    # Always clear keyframes/drivers on rotation_mode to prevent animation interference
    try:
        obj = bone.id_data  # Armature Object that owns this pose bone
        data_path = bone.path_from_id('rotation_mode')  # e.g., pose.bones["Bone"].rotation_mode

        # Remove any driver targeting rotation_mode
        try:
            if obj is not None:
                obj.driver_remove(data_path)
        except Exception:
            pass

        # Remove FCurves in active action and NLA strips that keyframe rotation_mode
        if obj is not None and obj.animation_data is not None:
            ad = obj.animation_data
            # Active action
            if ad.action is not None:
                for fc in list(ad.action.fcurves):
                    if fc.data_path == data_path:
                        ad.action.fcurves.remove(fc)
            # NLA strips' actions
            for track in ad.nla_tracks:
                for strip in track.strips:
                    act = strip.action
                    if act is not None:
                        for fc in list(act.fcurves):
                            if fc.data_path == data_path:
                                act.fcurves.remove(fc)
    except Exception as e:
        print(f"WARNING: Failed to clear keyframes/drivers on {bone.name}.rotation_mode: {e}")

    # Handle based on override flag
    if override:
        # OVERRIDE MODE: Permanently change to XYZ Euler
        original_mode = bone.rotation_mode
        
        if original_mode == 'QUATERNION':
            # Convert quaternion to euler and switch permanently
            current_euler = bone.rotation_quaternion.to_euler()
            bone.rotation_mode = 'XYZ'
            bone.rotation_euler = current_euler
            print(f"INFO: Converted {bone.name} from Quaternion to XYZ Euler rotation mode")
            return current_euler
        else:
            # Already XYZ Euler
            print(f"INFO: {bone.name} already in XYZ Euler mode")
            return bone.rotation_euler.copy()
    
    else:
        # NON-OVERRIDE MODE: Preserve original mode
        original_mode = bone.rotation_mode
        
        if original_mode == 'QUATERNION':
            # Convert quaternion to euler in-memory — NO mode switch needed.
            # Switching rotation_mode even temporarily causes a pose flicker
            # and may confuse the depsgraph.
            current_euler = bone.rotation_quaternion.to_euler('XYZ')
            print(f"INFO: Read {bone.name} quaternion as XYZ Euler (mode preserved, no flicker)")
            return current_euler
        elif original_mode == 'AXIS_ANGLE':
            # Convert axis-angle to euler in-memory
            aa = bone.rotation_axis_angle
            q = mathutils.Quaternion(aa[1:], aa[0])  # (w, axis) -> Quaternion
            current_euler = q.to_euler('XYZ')
            print(f"INFO: Read {bone.name} axis-angle as XYZ Euler (mode preserved, no flicker)")
            return current_euler
        else:
            # Already Euler: just return a copy
            print(f"INFO: Reading {bone.name} Euler values (mode preserved)")
            return bone.rotation_euler.copy()


def ensure_object_euler_rotation(obj):
    """Ensure an object is using Euler rotation mode and return the current euler values."""
    if obj.rotation_mode == 'QUATERNION':
        current_euler = obj.rotation_quaternion.to_euler()
        obj.rotation_mode = 'XYZ'
        obj.rotation_euler = current_euler
        print(f"INFO: Converted {obj.name} from Quaternion to Euler rotation mode")
        return current_euler
    else:
        return obj.rotation_euler.copy()

def get_selected_target_objects(context):
    """Get all selected objects when in Object Mode - used so 'Record Min/Max
    Pose' can auto-detect and record object transforms (not just pose bones)
    when the user is working in Object Mode instead of Pose Mode."""
    if context.mode != 'OBJECT':
        return []
    return list(context.selected_objects)


def get_selected_pose_bones(context):
    """Get all selected pose bones across ALL armatures in the scene.

    Returns (primary_obj, [(armature_obj, pose_bone), ...]) so callers can
    know which armature every bone belongs to.  The old single-return-value
    form is kept for back-compat: callers that only unpack two values still
    work because the second item is a list of (armature, bone) tuples.

    Also accepts the old call signature – if only one armature is in pose
    mode it behaves exactly as before.
    """
    def _is_selected(bone):
        try:
            if hasattr(bone.bone, 'select_get'):
                return bone.bone.select_get()
            if hasattr(bone.bone, 'select'):
                return bone.bone.select
            if hasattr(bone, 'select'):
                return bone.select
        except (AttributeError, RuntimeError):
            pass
        return False

    primary_obj = context.object
    result = []   # list of (armature_obj, pose_bone)

    # Walk every object in the scene that is currently in Pose Mode
    for obj in context.scene.objects:
        if obj.type != 'ARMATURE':
            continue
        # An armature is "in pose mode" when it is the active object in pose
        # mode, OR when it is a selected object that Blender has also put into
        # pose mode (multi-object edit / pose in Blender 2.9+).
        if obj.mode != 'POSE':
            continue
        for bone in obj.pose.bones:
            if _is_selected(bone):
                result.append((obj, bone))

    # Legacy callers do:  obj, selected_bones = get_selected_pose_bones(context)
    # and then use bone.location etc. directly.  Keep that working by returning
    # the primary object as first element and the list of (arm, bone) pairs as
    # second.  Callers that need multi-rig awareness iterate the pairs.
    return primary_obj, result
def detect_significant_changes(min_vals, max_vals, threshold_loc=0.001, threshold_rot=0.06, threshold_scale=0.01):
    """Detect which axes have significant changes between min and max values."""
    changes = []
    
    # Check location changes
    for i in range(3):
        diff = abs(max_vals['location'][i] - min_vals['location'][i])
        if diff > threshold_loc:
            changes.append(('location', i, min_vals['location'][i], max_vals['location'][i]))
    
    # Check rotation changes
    for i in range(3):
        diff = abs(max_vals['rotation'][i] - min_vals['rotation'][i])
        if diff > threshold_rot:
            changes.append(('rotation_euler', i, min_vals['rotation'][i], max_vals['rotation'][i]))
    
    # Check scale changes
    for i in range(3):
        diff = abs(max_vals['scale'][i] - min_vals['scale'][i])
        if diff > threshold_scale:
            changes.append(('scale', i, min_vals['scale'][i], max_vals['scale'][i]))
    
    return changes

def update_shapekey_value(self, context, is_min):
    """Update shape key value when min/max sliders change."""
    if self.shapekey_target_object and self.shapekey_name:
        obj = bpy.data.objects.get(self.shapekey_target_object)
        if obj and obj.data and hasattr(obj.data, 'shape_keys') and obj.data.shape_keys:
            key_block = obj.data.shape_keys.key_blocks.get(self.shapekey_name)
            if key_block:
                if is_min:
                    key_block.value = self.shapekey_min_value
                else:
                    key_block.value = self.shapekey_max_value



def validate_custom_path(path, context=None):
    """Validate if a custom path is accessible."""
    import bpy
    
    try:
        # Split the path and resolve step by step
        if path.startswith('bpy.'):
            # Remove 'bpy.' prefix and split
            path_parts = path[4:].split('.')
            
            # Start with bpy module
            current = bpy
            
            # Traverse the path
            for part in path_parts:
                if '[' in part and ']' in part:
                    # Handle array access like objects["Cube"]
                    attr_name = part.split('[')[0]
                    key = part.split('[')[1].split(']')[0].strip('"\'')
                    current = getattr(current, attr_name)[key]
                else:
                    # Regular attribute access
                    current = getattr(current, part)
            
            return True, type(current).__name__
        else:
            # Relative path - use active object
            if context and context.active_object:
                data_block = context.active_object
            else:
                data_block = bpy.context.active_object
                
            if not data_block:
                return False, "No active object available"
            
            result = data_block.path_resolve(path)
            return True, type(result).__name__
            
    except (AttributeError, KeyError, TypeError) as e:
        return False, f"Path not found: {str(e)}"
    except Exception as e:
        return False, f"Error: {str(e)}"




# Add these functions to core_functions.py

def get_mirrored_name(name):
    """Get the mirrored/opposite name for bones and shape keys following standard naming conventions."""
    if not name:
        return None
    
    # Define left/right patterns - order matters (more specific first)
    left_patterns = [
        # Underscores
        ('_Left', '_Right'), ('_left', '_right'), ('_L', '_R'), ('_l', '_r'),
        # Dots  
        ('.Left', '.Right'), ('.left', '.right'), ('.L', '.R'), ('.l', '.r'),
        # Dashes
        ('-Left', '-Right'), ('-left', '-right'), ('-L', '-R'), ('-l', '-r'),
        # Prefixes with underscores
        ('Left_', 'Right_'), ('left_', 'right_'), ('L_', 'R_'), ('l_', 'r_'),
        # Prefixes with dots
        ('Left.', 'Right.'), ('left.', 'right.'), ('L.', 'R.'), ('l.', 'r.'),
        # Prefixes with dashes
        ('Left-', 'Right-'), ('left-', 'right-'), ('L-', 'R-'), ('l-', 'r-'),
        # Plain words
        ('left', 'right'), ('Left', 'Right'),
        
        # Common 3D software patterns
        ('_lf', '_rt'), ('_LF', '_RT'), ('.lf', '.rt'), ('.LF', '.RT'),
        ('lf_', 'rt_'), ('LF_', 'RT_'), ('lf.', 'rt.'), ('LF.', 'RT.'),
        ('lf-', 'rt-'), ('LF-', 'RT-'), ('-lf', '-rt'), ('-LF', '-RT'),
        
        # Blender/Maya common patterns
        ('_side_L', '_side_R'), ('_side_l', '_side_r'), ('.side.L', '.side.R'), ('.side.l', '.side.r'),
        ('side_L_', 'side_R_'), ('side_l_', 'side_r_'), ('side.L.', 'side.R.'), ('side.l.', 'side.r.'),
        ('side-L-', 'side-R-'), ('side-l-', 'side-r-'), ('-side_L', '-side_R'), ('-side_l', '-side_r'),

        # Blender-specific patterns
        ('_L_', '_R_'), ('_l_', '_r_'), ('.L_', '.R_'), ('.l_', '.r_'),
        ('L_.', 'R_.'), ('l_.', 'r_.'),
        ('L_-', 'R_-'), ('l_-', 'r_-'),
        
       # Anatomical/Medical
        ('_sin', '_dex'), ('_SIN', '_DEX'), ('sin_', 'dex_'), ('SIN_', 'DEX_'),
        ('.sin', '.dex'), ('.SIN', '.DEX'), ('sin.', 'dex.'), ('SIN.', 'DEX.'),
        
        # Game engine patterns
        ('_lt', '_rt'), ('_LT', '_RT'), ('lt_', 'rt_'), ('LT_', 'RT_'),
        ('.lt', '.rt'), ('.LT', '.RT'), ('lt.', 'rt.'), ('LT.', 'RT.'),
        ('lt-', 'rt-'), ('LT-', 'RT-'), ('-lt', '-rt'), ('-LT', '-RT'),

        # Directional patterns
        ('_west', '_east'), ('_West', '_East'), ('_WEST', '_EAST'),
        ('west_', 'east_'), ('West_', 'East_'), ('WEST_', 'EAST_'),
        ('.west', '.east'), ('.West', '.East'), ('.WEST', '.EAST'),
        ('west.', 'east.'), ('West.', 'East.'), ('WEST.', 'EAST.'),

        # Port/Starboard (nautical)  ARGGGHH~
        ('_port', '_starboard'), ('_Port', '_Starboard'), ('_PORT', '_STARBOARD'),
        ('port_', 'starboard_'), ('Port_', 'Starboard_'), ('PORT_', 'STARBOARD_'),
        
        # A/B patterns
        ('_A', '_B'), ('_a', '_b'), ('A_', 'B_'), ('a_', 'b_'),
        ('.A', '.B'), ('.a', '.b'), ('A.', 'B.'), ('a.', 'b.'),
        ('A-', 'B-'), ('a-', 'b-'), ('-A', '-B'), ('-a', '-b'),
        
        # X/Y patterns (sometimes used for left/right... probrably shouldn't be, but whatever)
        ('_X', '_Y'), ('_x', '_y'), ('X_', 'Y_'), ('x_', 'y_'),
        ('.X', '.Y'), ('.x', '.y'), ('X.', 'Y.'), ('x.', 'y.'),
        
        # Parentheses patterns
        ('(L)', '(R)'), ('(l)', '(r)'), ('(Left)', '(Right)'), ('(left)', '(right)'),
        
        # Bracket patterns
        ('[L]', '[R]'), ('[l]', '[r]'), ('[Left]', '[Right]'), ('[left]', '[right]'),
        ('[1]', '[2]'), ('[A]', '[B]'), ('[a]', '[b]'),
        
        # Colon patterns
        (':L', ':R'), (':l', ':r'), (':Left', ':Right'), (':left', ':right'),
        ('L:', 'R:'), ('l:', 'r:'), ('Left:', 'Right:'), ('left:', 'right:'),
        
        # Space patterns (less common but possible)
        (' L', ' R'), (' l', ' r'), (' Left', ' Right'), (' left', ' right'),
        ('L ', 'R '), ('l ', 'r '), ('Left ', 'Right '), ('left ', 'right '),

        
        ('*l', '*r'), ('*L', '*R'),  # Asterisk patterns
        
        # Mixed case patterns
        ('_lEFT', '_rIGHT'), ('_LeFt', '_RiGhT'), ('lEFT_', 'rIGHT_'), ('LeFt_', 'RiGhT_'),
        
        # Double separator patterns
        ('__L', '__R'), ('__l', '__r'), ('..L', '..R'), ('..l', '..r'),
        ('--L', '--R'), ('--l', '--r'), ('L__', 'R__'), ('l__', 'r__'),
        
        # Pipe separator patterns
        ('|L', '|R'), ('|l', '|r'), ('L|', 'R|'), ('l|', 'r|'),
        ('|Left', '|Right'), ('|left', '|right'), ('Left|', 'Right|'), ('left|', 'right|'),
        
        # Hash patterns
        ('#L', '#R'), ('#l', '#r'), ('L#', 'R#'), ('l#', 'r#'),
        
        # At symbol patterns
        ('@L', '@R'), ('@l', '@r'), ('L@', 'R@'), ('l@', 'r@'),

        ('L', 'R'),  # Very general patterns at the end
    ]

    
    # Check for ending patterns first (more specific)
    for left_pattern, right_pattern in left_patterns:
        if name.endswith(left_pattern):
            return name[:-len(left_pattern)] + right_pattern
        elif name.endswith(right_pattern):
            return name[:-len(right_pattern)] + left_pattern
    
    # Check for starting patterns
    for left_pattern, right_pattern in left_patterns:
        if name.startswith(left_pattern):
            return right_pattern + name[len(left_pattern):]
        elif name.startswith(right_pattern):
            return left_pattern + name[len(right_pattern):]
    
    # No mirror pattern found
    return None

def mirror_source(props):
    """Mirror the source configuration to opposite side."""
    if props.from_bone:
        # Mirror bone source
        mirrored_bone = get_mirrored_name(props.from_bone)
        print(f"DEBUG: Mirroring source bone '{props.from_bone}' → '{mirrored_bone}'")
        
        if mirrored_bone:
            # Check if mirrored bone exists in the armature
            armature = bpy.data.objects.get(props.from_armature)
            if armature and armature.type == 'ARMATURE':
                if mirrored_bone in armature.pose.bones:
                    # Update to mirrored bone, keep all recorded values
                    props.from_bone = mirrored_bone
                    print(f"DEBUG: ✓ Source mirrored successfully")
                    return True, f"Mirrored to bone: {mirrored_bone}"
                else:
                    available_bones = [b.name for b in armature.pose.bones if mirrored_bone.lower() in b.name.lower()]
                    print(f"DEBUG: ✗ Mirror bone '{mirrored_bone}' not found. Similar: {available_bones[:3]}")
                    return False, f"Mirror bone '{mirrored_bone}' not found"
            else:
                return False, "Armature not found"
        else:
            return False, f"No mirror pattern found for: {props.from_bone}"
    
    elif props.from_object:
        # Mirror object source
        mirrored_object = get_mirrored_name(props.from_object)
        print(f"DEBUG: Mirroring source object '{props.from_object}' → '{mirrored_object}'")
        
        if mirrored_object:
            # Check if mirrored object exists
            if mirrored_object in bpy.data.objects:
                # Update to mirrored object, keep all recorded values
                props.from_object = mirrored_object
                print(f"DEBUG: ✓ Object source mirrored successfully")
                return True, f"Mirrored to object: {mirrored_object}"
            else:
                available_objects = [obj.name for obj in bpy.data.objects if mirrored_object.lower() in obj.name.lower()]
                print(f"DEBUG: ✗ Mirror object '{mirrored_object}' not found. Similar: {available_objects[:3]}")
                return False, f"Mirror object '{mirrored_object}' not found"
        else:
            return False, f"No mirror pattern found for: {props.from_object}"
    
    return False, "No source configured"

def mirror_pose_targets(props):
    """Mirror all pose targets to opposite side.

    Keys in to_data are "ArmatureName::BoneName".  We mirror only the
    bone-name part (after '::'), then write the result under the correct
    'ArmatureName::MirroredBoneName' key so create_drivers keeps working.
    """
    to_data = get_to_bones_data(props)
    mirrored_data = {}
    mirrored_count = 0
    skipped_bones = []

    print(f"DEBUG: Starting pose target mirror with {len(to_data)} entries")

    for key, bone_data in to_data.items():
        # Extract the real bone name from the key (handles both old bare keys
        # and new 'Armature::Bone' keys for backward compat).
        if '::' in key:
            armature_prefix, bare_bone_name = key.split('::', 1)
        else:
            armature_prefix = bone_data.get('armature', '')
            bare_bone_name  = key

        mirrored_bone = get_mirrored_name(bare_bone_name)
        print(f"DEBUG: Processing '{bare_bone_name}' → '{mirrored_bone}'")

        if mirrored_bone:
            armature_name = bone_data.get('armature') or armature_prefix
            armature = bpy.data.objects.get(armature_name) if armature_name else None

            if armature and armature.type == 'ARMATURE':
                if mirrored_bone in armature.pose.bones:
                    # Build the correct new key
                    new_key = f"{armature_name}::{mirrored_bone}"
                    new_data = bone_data.copy()
                    new_data['bone_name'] = mirrored_bone  # keep bone_name field in sync
                    mirrored_data[new_key] = new_data
                    mirrored_count += 1
                    print(f"DEBUG: ✓ Mirrored {key} → {new_key}")
                else:
                    mirrored_data[key] = bone_data
                    skipped_bones.append(bare_bone_name)
                    similar_bones = [b.name for b in armature.pose.bones
                                     if any(part in b.name.lower()
                                            for part in mirrored_bone.lower().split('_'))][:3]
                    print(f"DEBUG: ✗ Mirror bone '{mirrored_bone}' not found. Similar: {similar_bones}")
            else:
                mirrored_data[key] = bone_data
                skipped_bones.append(bare_bone_name)
                print(f"DEBUG: ✗ Armature '{armature_name}' not found or invalid")
        else:
            mirrored_data[key] = bone_data
            skipped_bones.append(bare_bone_name)
            print(f"DEBUG: ✗ No mirror pattern found for: {bare_bone_name}")

    set_to_bones_data(props, mirrored_data)

    print(f"DEBUG: Pose mirror complete - {mirrored_count} mirrored, {len(skipped_bones)} skipped")

    message = f"Mirrored {mirrored_count} bones"
    if skipped_bones:
        message += f", skipped {len(skipped_bones)} bones"
        if len(skipped_bones) <= 3:
            message += f": {', '.join(skipped_bones)}"
        else:
            message += f": {', '.join(skipped_bones[:3])} and {len(skipped_bones) - 3} more"

    return mirrored_count > 0, message


def mirror_shapekey_targets(props):
    """Mirror all shapekey targets to opposite side."""
    shapekey_data = get_shapekey_list_data(props)
    mirrored_data = {}
    mirrored_count = 0
    skipped_keys = []
    
    print(f"DEBUG: Starting shapekey mirror with {len(shapekey_data)} shape keys")
    
    for key, sk_data in shapekey_data.items():
        obj_name = sk_data['object']
        shapekey_name = sk_data['shapekey']
        
        # Try to mirror the shape key name
        mirrored_shapekey = get_mirrored_name(shapekey_name)
        print(f"DEBUG: Processing '{shapekey_name}' → '{mirrored_shapekey}'")
        
        if mirrored_shapekey:
            # Check if mirrored shape key exists
            obj = bpy.data.objects.get(obj_name)
            if (obj and obj.data and hasattr(obj.data, 'shape_keys') and 
                obj.data.shape_keys and mirrored_shapekey in obj.data.shape_keys.key_blocks):
                
                # Create new key for mirrored shape key
                new_key = f"{obj_name}:{mirrored_shapekey}"
                mirrored_data[new_key] = sk_data.copy()
                mirrored_data[new_key]['shapekey'] = mirrored_shapekey
                mirrored_count += 1
                print(f"DEBUG: ✓ Mirrored {shapekey_name} → {mirrored_shapekey}")
            else:
                # Keep original if mirror doesn't exist
                mirrored_data[key] = sk_data
                skipped_keys.append(shapekey_name)
                # Show available shape keys for debugging
                if obj and obj.data and hasattr(obj.data, 'shape_keys') and obj.data.shape_keys:
                    available_keys = [k.name for k in obj.data.shape_keys.key_blocks 
                                    if mirrored_shapekey.lower() in k.name.lower()][:3]
                    print(f"DEBUG: ✗ Mirror shape key '{mirrored_shapekey}' not found. Similar: {available_keys}")
                else:
                    print(f"DEBUG: ✗ Object '{obj_name}' has no shape keys")
        else:
            # Keep original if no mirror pattern
            mirrored_data[key] = sk_data
            skipped_keys.append(shapekey_name)
            print(f"DEBUG: ✗ No mirror pattern found for: {shapekey_name}")
    
    # Update the data
    set_shapekey_list_data(props, mirrored_data)
    
    print(f"DEBUG: Shapekey mirror complete - {mirrored_count} mirrored, {len(skipped_keys)} skipped")
    
    message = f"Mirrored {mirrored_count} shape keys"
    if skipped_keys:
        message += f", skipped {len(skipped_keys)} keys"
        if len(skipped_keys) <= 3:
            message += f": {', '.join(skipped_keys)}"
        else:
            message += f": {', '.join(skipped_keys[:3])} and {len(skipped_keys) - 3} more"
    
    return mirrored_count > 0, message

#---------------------------------------
# Driver Review / Scanning
#---------------------------------------
def _describe_driver_variable(var):
    """Return a short human readable description of a driver's source variable."""
    try:
        if not var.targets:
            return "Unknown source"
        tgt = var.targets[0]

        if var.type == 'TRANSFORMS':
            obj = tgt.id
            obj_name = obj.name if obj else "?"
            bone = tgt.bone_target or ""
            ttype = tgt.transform_type
            if bone:
                return f'{obj_name} \u203a bone "{bone}" ({ttype})'
            return f"{obj_name} ({ttype})"

        elif var.type == 'SINGLE_PROP':
            obj = tgt.id
            obj_name = obj.name if obj else "?"
            data_path = tgt.data_path or ""
            if data_path.startswith('['):
                return f"{obj_name}{data_path}"
            return f"{obj_name}.{data_path}"

        else:
            return f"{var.type}"
    except Exception:
        return "Unknown source"


def _driver_target_ok(var):
    """Check whether a driver variable's target(s) still resolve to something valid."""
    try:
        if not var.targets:
            return False
        for tgt in var.targets:
            if tgt.id is None:
                return False
            if var.type == 'TRANSFORMS' and tgt.bone_target:
                if not getattr(tgt.id, 'pose', None):
                    return False
                if tgt.bone_target not in tgt.id.pose.bones:
                    return False
        return True
    except Exception:
        return False


# Maps the id_type label we store back to the bpy.data collection to search
_EZDRV_ID_COLLECTIONS = {
    'OBJECT': 'objects',
    'SHAPE_KEY': 'shape_keys',
    'MATERIAL': 'materials',
    'NODE_GROUP': 'node_groups',
    'SCENE': 'scenes',
    'WORLD': 'worlds',
}


_AXIS_TO_LETTER = {0: 'X', 1: 'Y', 2: 'Z'}
_PROP_TO_TRANSFORM = {'location': 'LOC', 'rotation_euler': 'ROT', 'scale': 'SCALE'}


def _format_custom_prop_value(value):
    """Short display string for a custom property's current value."""
    if isinstance(value, bool):
        return "On" if value else "Off"
    if isinstance(value, float):
        return f"{value:.3f}"
    if isinstance(value, int):
        return str(value)
    # Arrays / strings / anything else - just show it, truncated if long
    s = str(value)
    return s if len(s) <= 24 else s[:21] + "..."


def _custom_prop_type_label(value):
    if isinstance(value, bool):
        return "Toggle"
    if isinstance(value, int):
        return "Integer"
    if isinstance(value, float):
        return "Float"
    if isinstance(value, str):
        return "String"
    return "Other"


def scan_custom_properties(target):
    """List every user-facing custom property on an object or pose bone,
    for the Custom Property Browser. Skips Blender's internal bookkeeping
    keys (anything starting with '_', like '_RNA_UI')."""
    if target is None:
        return []
    results = []
    for key in target.keys():
        if key.startswith('_'):
            continue
        try:
            value = target[key]
        except Exception:
            continue
        results.append({
            'name': key,
            'type_label': _custom_prop_type_label(value),
            'value_display': _format_custom_prop_value(value),
        })
    results.sort(key=lambda r: r['name'].lower())
    return results


_ID_TYPE_MAP = {
    'Object': 'OBJECT', 'Mesh': 'MESH', 'Armature': 'ARMATURE', 'Material': 'MATERIAL',
    'ShaderNodeTree': 'NODETREE', 'GeometryNodeTree': 'NODETREE', 'CompositorNodeTree': 'NODETREE',
    'NodeTree': 'NODETREE', 'Scene': 'SCENE', 'World': 'WORLD', 'Key': 'KEY', 'Image': 'IMAGE',
    'Light': 'LIGHT', 'Camera': 'CAMERA', 'Curve': 'CURVE', 'Lattice': 'LATTICE',
    'Speaker': 'SPEAKER', 'Texture': 'TEXTURE', 'Text': 'TEXT',
}


def _infer_id_type_string(id_block):
    """Map a resolved ID datablock instance to the RNA id_type enum string
    DriverTarget.id_type expects (walks the class MRO so subclassed node
    tree types like ShaderNodeTree still resolve to 'NODETREE')."""
    for cls in type(id_block).__mro__:
        name = getattr(cls, '__name__', '')
        if name in _ID_TYPE_MAP:
            return _ID_TYPE_MAP[name]
    return 'OBJECT'


def parse_custom_path_source(path_str):
    """Resolve an arbitrary custom path (same syntax/eyedropper as the Path
    List target picker) into a source_config dict for use as a driver
    SOURCE. Reuses the general-purpose parse_target_path resolver instead of
    the narrower parse_source_path, since a custom-path source can point at
    node inputs, constraints, modifiers, scene props, etc - not just the
    bone/object/custom-prop/shapekey shapes parse_source_path understands.
    """
    data_block, data_path, index = parse_target_path(path_str)
    if not data_block:
        return None

    full_data_path = f"{data_path}[{index}]" if (index is not None and index >= 0) else data_path

    return {
        'type': 'custom_path',
        'id_block': data_block,
        'id_type': _infer_id_type_string(data_block),
        'data_path': full_data_path,
    }


def resolve_multi_source_slot_for_constraint(slot):
    """For one multi-source slot, figure out whether it's a bone/object
    transform source and, if so, return what's needed to add a Limit/Lock
    constraint to it: {'is_bone', 'armature', 'bone_name', 'object', 'axis_info'}.

    Returns None if the slot isn't a transform source - custom property and
    shape key sources have no transform channel to constrain, so "Lock to
    One Axis" / "Lock Recorded" can't apply to them; those slots are skipped
    with a message rather than silently ignored.
    """
    source_config = parse_source_path(slot.get('from_path', ''), slot.get('source_name', ''))
    if not source_config or source_config.get('type') not in ('bone', 'object'):
        return None

    prop = source_config.get('property')
    index = source_config.get('index')
    transform = _PROP_TO_TRANSFORM.get(prop)
    axis = _AXIS_TO_LETTER.get(index)
    if not transform or axis is None:
        return None

    axis_info = {'transform': transform, 'axis': axis, 'index': index}

    if source_config['type'] == 'bone':
        return {
            'is_bone': True,
            'armature': source_config['armature'],
            'bone_name': source_config['bone_name'],
            'object': None,
            'axis_info': axis_info,
        }
    else:
        return {
            'is_bone': False,
            'armature': None,
            'bone_name': None,
            'object': source_config['object'],
            'axis_info': axis_info,
        }


def find_driver_fcurve(id_block, data_path, array_index):
    """Find the exact driver FCurve on an ID block matching a data_path +
    array_index - used by the Driver Review 'edit expression' feature to
    re-locate the fcurve the user is looking at."""
    anim = getattr(id_block, 'animation_data', None)
    if not anim:
        return None
    for fcurve in anim.drivers:
        if fcurve.data_path == data_path and fcurve.array_index == array_index:
            return fcurve
    return None


def resolve_easydriver_id_block(id_name, id_type):
    """Re-locate the ID datablock a reviewed driver lives on, by name + type."""
    if id_type == 'MATERIAL_NODES':
        for mat in bpy.data.materials:
            if mat.node_tree and mat.node_tree.name == id_name:
                return mat.node_tree
        return None

    coll_name = _EZDRV_ID_COLLECTIONS.get(id_type)
    if not coll_name:
        return None
    return getattr(bpy.data, coll_name).get(id_name)


_AXIS_NAMES = ['X', 'Y', 'Z']
_TRANSFORM_LABELS = {'location': 'Location', 'rotation_euler': 'Rotation', 'scale': 'Scale'}


def _read_current_value(id_block, data_path, array_index):
    """Best-effort read of a property's live current value, for display only."""
    try:
        resolved = id_block.path_resolve(data_path)
        if array_index is not None and array_index >= 0:
            try:
                resolved = resolved[array_index]
            except (TypeError, IndexError):
                pass
        if isinstance(resolved, float):
            return f"{resolved:.3f}"
        if isinstance(resolved, bool):
            return "On" if resolved else "Off"
        return str(resolved)
    except Exception:
        return "?"


def _humanize_target(id_block, id_type_label, data_path, array_index):
    """Turn a raw driver data_path (e.g. pose.bones["Ear.L"].location) into a
    clean 'Object › Bone — Property Axis' style label, plus its live value -
    instead of showing the raw bpy path syntax in the Driver Review list."""
    axis = _AXIS_NAMES[array_index] if array_index is not None and 0 <= array_index < 3 else None
    current = _read_current_value(id_block, data_path, array_index)

    m = re.match(r'^pose\.bones\["([^"]+)"\]\.(location|rotation_euler|scale)$', data_path)
    if m:
        bone_name, prop = m.groups()
        label = _TRANSFORM_LABELS.get(prop, prop)
        axis_str = f" {axis}" if axis else ""
        return f"{id_block.name} \u203a {bone_name} \u2014 {label}{axis_str}", current

    m = re.match(r'^(location|rotation_euler|scale)$', data_path)
    if m:
        prop = m.group(1)
        label = _TRANSFORM_LABELS.get(prop, prop)
        axis_str = f" {axis}" if axis else ""
        return f"{id_block.name} \u2014 {label}{axis_str}", current

    m = re.match(r'^pose\.bones\["([^"]+)"\]\["([^"]+)"\]$', data_path)
    if m:
        bone_name, prop_name = m.groups()
        return f'{id_block.name} \u203a {bone_name}["{prop_name}"]', current

    m = re.match(r'^\["([^"]+)"\]$', data_path)
    if m:
        prop_name = m.group(1)
        return f'{id_block.name}["{prop_name}"]', current

    m = re.match(r'^(?:data\.shape_keys\.)?key_blocks\["([^"]+)"\]\.value$', data_path)
    if m:
        key_name = m.group(1)
        return f"{id_block.name} \u203a {key_name} (Shape Key)", current

    m = re.match(r'^(?:node_tree\.)?nodes\["([^"]+)"\]\.inputs\[(\d+)\]\.default_value$', data_path)
    if m:
        node_name, input_idx = m.groups()
        return f"{id_block.name} \u203a {node_name} \u2014 Input {input_idx}", current

    # Fallback for anything not matched above - still trims the path down
    # to its last segment instead of showing the full bpy path.
    tail = data_path.rsplit('.', 1)[-1]
    axis_str = f"[{axis}]" if axis else (f"[{array_index}]" if (array_index is not None and array_index >= 0) else "")
    return f"{id_block.name} \u2014 {tail}{axis_str}", current


def scan_easydriver_drivers():
    """Scan the current .blend for drivers created by Easy Driver.

    This is a pure scan of live driver/fcurve data - it does not rely on
    any addon-side runtime state, so results are identical whether the
    file was just opened, reloaded, or has been open the whole session.
    """
    results = []

    def _scan_id_block(id_block, id_type_label):
        anim = getattr(id_block, 'animation_data', None)
        if not anim or not anim.drivers:
            return
        for fcurve in anim.drivers:
            driver = fcurve.driver
            expr = driver.expression or ""
            match = _EZDRV_MARKER_RE.search(expr)
            if not match:
                continue
            curve_type = match.group(1)

            source_desc = "Unknown source"
            source_ok = False
            if driver.variables:
                var = driver.variables[0]
                source_desc = _describe_driver_variable(var)
                source_ok = _driver_target_ok(var)

            idx = fcurve.array_index
            clean_target, current_value = _humanize_target(id_block, id_type_label, fcurve.data_path, idx)

            results.append({
                'id_name': id_block.name,
                'id_type': id_type_label,
                'data_path': fcurve.data_path,
                'array_index': idx,
                'curve_type': curve_type,
                'source_desc': source_desc,
                'target_desc': f"{clean_target}  =  {current_value}",
                'expression': expr,
                'expr_valid': bool(driver.is_valid),
                'source_valid': source_ok,
            })

    # Objects cover object transform/custom-prop targets, AND armature
    # pose-bone drivers (bone driver fcurves live on the armature OBJECT's
    # animation_data, keyed by a pose.bones[...] data_path).
    for obj in bpy.data.objects:
        _scan_id_block(obj, 'OBJECT')

    # Shape keys are their own ID datablock (bpy.types.Key)
    for key in bpy.data.shape_keys:
        _scan_id_block(key, 'SHAPE_KEY')

    # Materials + their (often embedded) node trees
    for mat in bpy.data.materials:
        _scan_id_block(mat, 'MATERIAL')
        if getattr(mat, 'node_tree', None):
            _scan_id_block(mat.node_tree, 'MATERIAL_NODES')

    # Shared node groups
    for ng in bpy.data.node_groups:
        _scan_id_block(ng, 'NODE_GROUP')

    # Scenes and worlds (generic Path List targets can point here too)
    for scene in bpy.data.scenes:
        _scan_id_block(scene, 'SCENE')
    for world in bpy.data.worlds:
        _scan_id_block(world, 'WORLD')

    return results
