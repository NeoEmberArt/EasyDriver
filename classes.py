import bpy
import re
import bpy_extras.view3d_utils
import math
from .core_functions import (
    get_selected_pose_bones, ensure_euler_rotation, ensure_object_euler_rotation,
    detect_significant_changes, get_to_bones_data, set_to_bones_data,
    get_shapekey_list_data, set_shapekey_list_data, get_path_list_data,
    set_path_list_data, validate_custom_path, createDriver, update_shapekey_value, auto_detect_path_type,
    update_fine_tune_min_value, update_fine_tune_max_value, update_fine_tune_axis, 
    update_fine_tune_object_min_value, update_fine_tune_object_max_value, 
    update_fine_tune_object_axis, parse_target_path, get_mirrored_name, mirror_source, mirror_pose_targets, mirror_shapekey_targets
)


#---------------------------------------
# List Properties/Variables here
#---------------------------------------
class DriverRecorderProperties(bpy.types.PropertyGroup):
    # Add this where you register other scene properties
    bpy.types.Scene.source_fine_tune_mode = bpy.props.BoolProperty(
        name="Source Fine Tune Mode",
        default=False
    )
    # Bone fine tune properties
    fine_tune_min_value: bpy.props.FloatProperty(
        name="Min Value",
        update=update_fine_tune_min_value
    )
    fine_tune_max_value: bpy.props.FloatProperty(
        name="Max Value", 
        update=update_fine_tune_max_value
    )
    fine_tune_axis: bpy.props.EnumProperty(
        name="Axis",
        items=[
            ("LOC_X", "Loc X", "Location X"),
            ("LOC_Y", "Loc Y", "Location Y"), 
            ("LOC_Z", "Loc Z", "Location Z"),
            ("ROT_X", "Rot X", "Rotation X"),
            ("ROT_Y", "Rot Y", "Rotation Y"),
            ("ROT_Z", "Rot Z", "Rotation Z"),
        ],
        update=update_fine_tune_axis
    )

    # Object fine tune properties
    fine_tune_object_min_value: bpy.props.FloatProperty(
        name="Min Value",
        update=update_fine_tune_object_min_value
    )
    fine_tune_object_max_value: bpy.props.FloatProperty(
        name="Max Value",
        update=update_fine_tune_object_max_value
    )
    fine_tune_object_axis: bpy.props.EnumProperty(
        name="Axis",
        items=[
            ("LOC_X", "Loc X", "Location X"),
            ("LOC_Y", "Loc Y", "Location Y"),
            ("LOC_Z", "Loc Z", "Location Z"), 
            ("ROT_X", "Rot X", "Rotation X"),
            ("ROT_Y", "Rot Y", "Rotation Y"),
            ("ROT_Z", "Rot Z", "Rotation Z"),
        ],
        update=update_fine_tune_object_axis
    )

    """Property group for driver recording."""
    object_eyedropper_active: bpy.props.BoolProperty(
        name="Object Eyedropper Active",
        description="Whether the object eyedropper is currently active",
        default=False
    )
    # FROM source type selection
    from_source_type: bpy.props.EnumProperty(
        name="Source Type",
        items=[
            ('BONE', 'Bone Transform', 'Use bone transforms as source'),
            ('OBJECT', 'Object Transform', 'Use object transforms as source')
        ],
        default='BONE'
    )
    path_eyedropper_active: bpy.props.BoolProperty(
        name="Path Eyedropper Active",
        description="Whether the path eyedropper is currently listening for changes",
        default=False
    )
    # FROM bone data
    from_armature: bpy.props.StringProperty(name="From Armature")
    from_bone: bpy.props.StringProperty(name="From Bone")
    from_has_min: bpy.props.BoolProperty(default=False)
    from_has_max: bpy.props.BoolProperty(default=False)
    from_min_location: bpy.props.FloatVectorProperty(size=3)
    from_max_location: bpy.props.FloatVectorProperty(size=3)
    from_min_rotation: bpy.props.FloatVectorProperty(size=3)
    from_max_rotation: bpy.props.FloatVectorProperty(size=3)
    from_detected_axis: bpy.props.StringProperty(default="")  # e.g., "LOC X"
    
    # FROM object data
    from_object: bpy.props.StringProperty(name="From Object")
    from_object_has_min: bpy.props.BoolProperty(default=False)
    from_object_has_max: bpy.props.BoolProperty(default=False)
    from_object_min_location: bpy.props.FloatVectorProperty(size=3)
    from_object_max_location: bpy.props.FloatVectorProperty(size=3)
    from_object_min_rotation: bpy.props.FloatVectorProperty(size=3)
    from_object_max_rotation: bpy.props.FloatVectorProperty(size=3)
    from_object_detected_axis: bpy.props.StringProperty(default="")
    
    # Target type selection
    target_type: bpy.props.EnumProperty(
        name="Target Type",
        items=[
            ('CUSTOM_POSE', 'Custom Pose', 'Drive bone transforms'),
            ('SHAPEKEY_LIST', 'Shapekey List', 'Drive shape keys'),
            ('PATH_LIST', 'Path List', 'Drive custom paths')
        ],
        default='CUSTOM_POSE'
    )
    
    # Custom Pose data (JSON string)
    to_bones_data: bpy.props.StringProperty(default="{}")
    
    # Shapekey data - changed to StringProperty for searchable dropdown
    shapekey_target_object: bpy.props.StringProperty(
        name="Target Object",
        description="Object with shape keys"
    )
    
    shapekey_name: bpy.props.StringProperty(
        name="Shape Key",
        description="Shape key to drive"
    )
    
    shapekey_min_value: bpy.props.FloatProperty(
        name="Min Value",
        default=0.0,
        min=0.0,
        max=1.0,
        update=lambda self, context: update_shapekey_value(self, context, True)
    )
    
    shapekey_max_value: bpy.props.FloatProperty(
        name="Max Value", 
        default=1.0,
        min=0.0,
        max=1.0,
        update=lambda self, context: update_shapekey_value(self, context, False)
    )
    
    # Shapekey list data (JSON string)
    shapekey_list_data: bpy.props.StringProperty(default="{}")
    
    # Path List data
    custom_path_input: bpy.props.StringProperty(
        name="Custom Path",
        description="Enter a custom Blender path (e.g., bpy.data.objects[\"Cube\"].hide_viewport)"
    )
    
    path_value_type: bpy.props.EnumProperty(
        name="Value Type",
        items=[
            ('FLOAT', 'Float Range', 'Use min/max float values'),
            ('BOOLEAN', 'Boolean Toggle', 'Use boolean on/off values')
        ],
        default='FLOAT'
    )
    
    path_min_value: bpy.props.FloatProperty(
        name="Min Value",
        default=0.0
    )
    
    path_max_value: bpy.props.FloatProperty(
        name="Max Value",
        default=1.0
    )
    
    path_false_value: bpy.props.FloatProperty(
        name="False Value",
        default=0.0,
        description="Value when driver input is at minimum"
    )
    
    path_true_value: bpy.props.FloatProperty(
        name="True Value", 
        default=1.0,
        description="Value when driver input is at maximum"
    )
    
    # Path list data (JSON string)
    path_list_data: bpy.props.StringProperty(default="{}")

#---------------------------------------
# EyeDropper Functions
#---------------------------------------
class ANIM_OT_object_eyedropper(bpy.types.Operator):
    """Eyedropper tool to select objects by clicking in the viewport"""
    bl_idname = "anim.object_eyedropper"
    bl_label = "Object Eyedropper"
    bl_description = "Click on an object in the viewport to select it"
    bl_options = {'REGISTER', 'UNDO'}
    
    # Property to specify which field to fill
    target_property: bpy.props.StringProperty(default="shapekey_target_object")
    
    def modal(self, context, event):
        context.area.tag_redraw()
        
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            # Allow navigation
            return {'PASS_THROUGH'}
        
        elif event.type == 'MOUSEMOVE':
            # Update cursor position
            return {'RUNNING_MODAL'}
        
        elif event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            # Perform raycast to find object under mouse
            result = self.raycast_object(context, event)
            if result:
                # Set the target property
                props = context.scene.driver_recorder_props
                setattr(props, self.target_property, result.name)
                
                self.report({'INFO'}, f"Selected object: {result.name}")
                self.finish(context)
                return {'FINISHED'}
            else:
                self.report({'WARNING'}, "No object under cursor")
        
        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            # Cancel
            self.report({'INFO'}, "Object selection cancelled")
            self.finish(context)
            return {'CANCELLED'}
        
        return {'RUNNING_MODAL'}
    
    def invoke(self, context, event):
        if context.area.type == 'VIEW_3D':
            # Set cursor to eyedropper
            context.window.cursor_modal_set('EYEDROPPER')
            
            # Set active state
            props = context.scene.driver_recorder_props
            props.object_eyedropper_active = True
            
            context.window_manager.modal_handler_add(self)
            self.report({'INFO'}, "Click on an object to select it (ESC to cancel)")
            return {'RUNNING_MODAL'}
        else:
            self.report({'WARNING'}, "View3D not found, cannot run operator")
            return {'CANCELLED'}
    
    def finish(self, context):
        """Clean up when finished"""
        # Restore cursor
        context.window.cursor_modal_restore()
        
        # Clear active state
        props = context.scene.driver_recorder_props
        props.object_eyedropper_active = False
    
    def raycast_object(self, context, event):
        """Perform raycast to find object under mouse cursor"""
        # Get the region and region_3d
        region = context.region
        region_3d = context.space_data.region_3d
        
        # Get mouse coordinates
        coord = (event.mouse_region_x, event.mouse_region_y)
        
        # Convert 2D mouse position to 3D ray
        view_vector = bpy_extras.view3d_utils.region_2d_to_vector_3d(region, region_3d, coord)
        ray_origin = bpy_extras.view3d_utils.region_2d_to_origin_3d(region, region_3d, coord)
        
        # Perform raycast
        depsgraph = context.evaluated_depsgraph_get()
        result, location, normal, index, obj, matrix = context.scene.ray_cast(
            depsgraph, ray_origin, view_vector
        )
        
        if result and obj:
            # Return the original object (not evaluated)
            return bpy.data.objects.get(obj.name)
        
        return None

class ANIM_OT_path_eyedropper(bpy.types.Operator):
    """Eyedropper tool to capture property data paths by detecting changes"""
    bl_idname = "anim.path_eyedropper"
    bl_label = "Path Eyedropper"
    bl_description = "Click and change any property to capture its data path"
    bl_options = {'REGISTER', 'UNDO'}

    _timer = None
    _initial_state = {}
    
    def modal(self, context, event):
        if event.type == 'ESC':
            self.cancel(context)
            return {'CANCELLED'}
        
        if event.type == 'TIMER':
            # Check for changes
            detected_path = self.detect_changes(context)
            if detected_path:
                # Set the detected path
                props = context.scene.driver_recorder_props
                props.custom_path_input = detected_path
                
                self.report({'INFO'}, f"Captured path: {detected_path}")
                self.finish(context)
                return {'FINISHED'}
        
        return {'PASS_THROUGH'}
    
    def invoke(self, context, event):
        # Set listening state
        props = context.scene.driver_recorder_props
        props.path_eyedropper_active = True
        
        # Store initial state
        self.capture_initial_state(context)
        
        # Add timer
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        
        self.report({'INFO'}, "Eyedropper active - change any property to capture its path")
        return {'RUNNING_MODAL'}
    
    def cancel(self, context):
        self.finish(context)
    
    def finish(self, context):
        # Clean up
        props = context.scene.driver_recorder_props
        props.path_eyedropper_active = False
        
        if self._timer:
            wm = context.window_manager
            wm.event_timer_remove(self._timer)
            self._timer = None
        
        # Clear state
        self._initial_state.clear()
    
    def safe_copy_value(self, value):
        """Safely copy a value, handling different types"""
        try:
            if hasattr(value, 'copy'):
                return value.copy()
            elif hasattr(value, '__len__') and not isinstance(value, str):
                return list(value)
            else:
                return value
        except:
            return value
    
    def values_equal(self, val1, val2, tolerance=0.001):
        """Compare two values with tolerance for floats"""
        try:
            if hasattr(val1, '__len__') and hasattr(val2, '__len__') and not isinstance(val1, str):
                if len(val1) != len(val2):
                    return False
                return all(abs(a - b) <= tolerance for a, b in zip(val1, val2))
            elif isinstance(val1, float) or isinstance(val2, float):
                return abs(val1 - val2) <= tolerance
            else:
                return val1 == val2
        except:
            return val1 == val2
    
    def capture_initial_state(self, context):
        """Capture initial state of various properties"""
        self._initial_state.clear()
        
        # Monitor all objects
        for obj in context.view_layer.objects:
            obj_data = {}
            
            # Basic object properties
            obj_data['location'] = self.safe_copy_value(obj.location)
            obj_data['rotation_euler'] = self.safe_copy_value(obj.rotation_euler)
            obj_data['scale'] = self.safe_copy_value(obj.scale)
            obj_data['hide_viewport'] = obj.hide_viewport
            obj_data['hide_render'] = obj.hide_render
            
            # Display properties
            if hasattr(obj, 'display'):
                display_props = ['show_shadows', 'show_in_front', 'show_wire', 'show_all_edges']
                obj_data['display'] = {}
                for prop in display_props:
                    if hasattr(obj.display, prop):
                        obj_data['display'][prop] = getattr(obj.display, prop)
            
            # Collision properties
            if hasattr(obj, 'collision') and obj.collision:
                collision_props = ['absorption', 'damping_factor', 'damping_random', 'friction_factor', 
                                 'friction_random', 'permeability', 'stickiness', 'thickness_inner', 
                                 'thickness_outer', 'use']
                obj_data['collision'] = {}
                for prop in collision_props:
                    if hasattr(obj.collision, prop):
                        obj_data['collision'][prop] = self.safe_copy_value(getattr(obj.collision, prop))
            
            # Rigid body properties
            if hasattr(obj, 'rigid_body') and obj.rigid_body:
                rb_props = ['mass', 'friction', 'restitution', 'linear_damping', 'angular_damping', 
                           'use_margin', 'collision_margin', 'kinematic', 'enabled']
                obj_data['rigid_body'] = {}
                for prop in rb_props:
                    if hasattr(obj.rigid_body, prop):
                        obj_data['rigid_body'][prop] = self.safe_copy_value(getattr(obj.rigid_body, prop))
            
            # Constraints
            if obj.constraints:
                obj_data['constraints'] = {}
                for constraint in obj.constraints:
                    const_data = {
                        'influence': constraint.influence,
                        'mute': constraint.mute
                    }
                    if hasattr(constraint, 'target'):
                        const_data['target'] = constraint.target
                    obj_data['constraints'][constraint.name] = const_data
            
            # Pose bone constraints (for armatures)
            if obj.type == 'ARMATURE' and obj.pose:
                obj_data['pose_bones'] = {}
                for pose_bone in obj.pose.bones:
                    pose_bone_data = {}
                    
                    if pose_bone.constraints:
                        pose_bone_data['constraints'] = {}
                        for constraint in pose_bone.constraints:
                            const_data = {
                                'influence': constraint.influence,
                                'mute': constraint.mute
                            }
                            pose_bone_data['constraints'][constraint.name] = const_data
                    
                    obj_data['pose_bones'][pose_bone.name] = pose_bone_data
            
            # Modifiers
            if obj.modifiers:
                obj_data['modifiers'] = {}
                for modifier in obj.modifiers:
                    mod_data = {
                        'show_viewport': modifier.show_viewport,
                        'show_render': modifier.show_render
                    }
                    
                    # Common modifier properties
                    mod_props = ['strength', 'factor', 'offset', 'ratio', 'levels', 'angle_limit', 
                               'iterations', 'lambda_factor', 'lambda_border', 'use_x', 'use_y', 'use_z']
                    for prop in mod_props:
                        if hasattr(modifier, prop):
                            mod_data[prop] = self.safe_copy_value(getattr(modifier, prop))
                    
                    obj_data['modifiers'][modifier.name] = mod_data
            
            self._initial_state[f"objects.{obj.name}"] = obj_data
        
        # Monitor armatures
        for armature in bpy.data.armatures:
            arm_data = {}
            
            # Armature display properties
            arm_data['show_bone_custom_shapes'] = armature.show_bone_custom_shapes
            
            # Bone collections visibility
            arm_data['collections'] = {}
            collections_attr = None
            if hasattr(armature, 'collections_all'):
                collections_attr = 'collections_all'
            elif hasattr(armature, 'collections'):
                collections_attr = 'collections'
            
            if collections_attr:
                collections = getattr(armature, collections_attr)
                for collection in collections:
                    arm_data['collections'][collection.name] = {
                        'is_visible': collection.is_visible,
                        'attr_name': collections_attr  # Store which attribute to use
                    }
            
            # Bone properties
            arm_data['bones'] = {}
            for bone in armature.bones:
                bone_props = ['hide_select', 'hide', 'use_deform', 'use_inherit_rotation', 
                             'use_inherit_scale', 'use_local_location', 'use_relative_parent']
                bone_data = {}
                for prop in bone_props:
                    if hasattr(bone, prop):
                        bone_data[prop] = getattr(bone, prop)
                arm_data['bones'][bone.name] = bone_data
            
            self._initial_state[f"armatures.{armature.name}"] = arm_data
        
        # Monitor materials
        for mat in bpy.data.materials:
            if mat.use_nodes and mat.node_tree:
                mat_data = {'nodes': {}}
                
                for node in mat.node_tree.nodes:
                    node_data = {}
                    
                    # Node mute
                    if hasattr(node, 'mute'):
                        node_data['mute'] = node.mute
                    
                    # Input values
                    if hasattr(node, 'inputs'):
                        node_data['inputs'] = {}
                        for i, input_socket in enumerate(node.inputs):
                            if hasattr(input_socket, 'default_value'):
                                try:
                                    node_data['inputs'][i] = self.safe_copy_value(input_socket.default_value)
                                except:
                                    pass
                    
                    mat_data['nodes'][node.name] = node_data
                
                self._initial_state[f"materials.{mat.name}"] = mat_data
        
        # Monitor scenes
        for scene in bpy.data.scenes:
            scene_data = {}
            
            # Frame properties
            scene_data['frame_current'] = scene.frame_current
            scene_data['frame_start'] = scene.frame_start
            scene_data['frame_end'] = scene.frame_end
            
            # Physics properties
            scene_data['use_gravity'] = scene.use_gravity
            scene_data['gravity'] = self.safe_copy_value(scene.gravity)
            
            # Render engine properties
            if hasattr(scene, 'eevee'):
                eevee_props = ['taa_samples', 'taa_render_samples', 'use_taa_reprojection', 
                              'use_ssr', 'use_ssr_refraction', 'use_bloom', 'use_motion_blur']
                scene_data['eevee'] = {}
                for prop in eevee_props:
                    if hasattr(scene.eevee, prop):
                        scene_data['eevee'][prop] = getattr(scene.eevee, prop)
            
            if hasattr(scene, 'cycles'):
                cycles_props = ['samples', 'preview_samples', 'use_denoising', 'denoiser']
                scene_data['cycles'] = {}
                for prop in cycles_props:
                    if hasattr(scene.cycles, prop):
                        scene_data['cycles'][prop] = getattr(scene.cycles, prop)
            
            self._initial_state[f"scenes.{scene.name}"] = scene_data

    def detect_changes(self, context):
        """Detect what property has changed and return its data path"""
        
        # Check objects
        for obj in context.view_layer.objects:
            obj_key = f"objects.{obj.name}"
            if obj_key not in self._initial_state:
                continue
                
            initial_obj = self._initial_state[obj_key]
            
            # Basic properties
            basic_props = ['location', 'rotation_euler', 'scale', 'hide_viewport', 'hide_render']
            for prop in basic_props:
                if prop in initial_obj:
                    current_val = getattr(obj, prop)
                    if not self.values_equal(current_val, initial_obj[prop]):
                        return f'bpy.data.objects["{obj.name}"].{prop}'
            
            # Display properties
            if 'display' in initial_obj and hasattr(obj, 'display'):
                for prop, initial_val in initial_obj['display'].items():
                    if hasattr(obj.display, prop):
                        current_val = getattr(obj.display, prop)
                        if current_val != initial_val:
                            return f'bpy.data.objects["{obj.name}"].display.{prop}'
            
            # Collision properties
            if 'collision' in initial_obj and hasattr(obj, 'collision') and obj.collision:
                for prop, initial_val in initial_obj['collision'].items():
                    if hasattr(obj.collision, prop):
                        current_val = getattr(obj.collision, prop)
                        if not self.values_equal(current_val, initial_val):
                            return f'bpy.data.objects["{obj.name}"].collision.{prop}'
            
            # Rigid body properties
            if 'rigid_body' in initial_obj and hasattr(obj, 'rigid_body') and obj.rigid_body:
                for prop, initial_val in initial_obj['rigid_body'].items():
                    if hasattr(obj.rigid_body, prop):
                        current_val = getattr(obj.rigid_body, prop)
                        if not self.values_equal(current_val, initial_val):
                            return f'bpy.data.objects["{obj.name}"].rigid_body.{prop}'
            
            # Constraints
            if 'constraints' in initial_obj and obj.constraints:
                for constraint in obj.constraints:
                    if constraint.name in initial_obj['constraints']:
                        initial_const = initial_obj['constraints'][constraint.name]
                        
                        if not self.values_equal(constraint.influence, initial_const['influence']):
                            return f'bpy.data.objects["{obj.name}"].constraints["{constraint.name}"].influence'
                        
                        if constraint.mute != initial_const['mute']:
                            return f'bpy.data.objects["{obj.name}"].constraints["{constraint.name}"].mute'
            
            # Pose bone constraints
            if 'pose_bones' in initial_obj and obj.type == 'ARMATURE' and obj.pose:
                for pose_bone in obj.pose.bones:
                    if pose_bone.name in initial_obj['pose_bones']:
                        initial_pose_bone = initial_obj['pose_bones'][pose_bone.name]
                        
                        if 'constraints' in initial_pose_bone and pose_bone.constraints:
                            for constraint in pose_bone.constraints:
                                if constraint.name in initial_pose_bone['constraints']:
                                    initial_const = initial_pose_bone['constraints'][constraint.name]
                                    
                                    if not self.values_equal(constraint.influence, initial_const['influence']):
                                        return f'bpy.data.objects["{obj.name}"].pose.bones["{pose_bone.name}"].constraints["{constraint.name}"].influence'
                                    
                                    if constraint.mute != initial_const['mute']:
                                        return f'bpy.data.objects["{obj.name}"].pose.bones["{pose_bone.name}"].constraints["{constraint.name}"].mute'
            
            # Modifiers
            if 'modifiers' in initial_obj and obj.modifiers:
                for modifier in obj.modifiers:
                    if modifier.name in initial_obj['modifiers']:
                        initial_mod = initial_obj['modifiers'][modifier.name]
                        
                        for prop, initial_val in initial_mod.items():
                            if hasattr(modifier, prop):
                                current_val = getattr(modifier, prop)
                                if not self.values_equal(current_val, initial_val):
                                    return f'bpy.data.objects["{obj.name}"].modifiers["{modifier.name}"].{prop}'
        
        # Check armatures
        for armature in bpy.data.armatures:
            arm_key = f"armatures.{armature.name}"
            if arm_key not in self._initial_state:
                continue
                
            initial_arm = self._initial_state[arm_key]
            
            # Armature display properties
            if 'show_bone_custom_shapes' in initial_arm:
                if armature.show_bone_custom_shapes != initial_arm['show_bone_custom_shapes']:
                    return f'bpy.data.armatures["{armature.name}"].show_bone_custom_shapes'
            
            # Bone collections visibility
            if 'collections' in initial_arm:
                for collection_name, initial_collection in initial_arm['collections'].items():
                    attr_name = initial_collection.get('attr_name', 'collections_all')
                    
                    if hasattr(armature, attr_name):
                        collections = getattr(armature, attr_name)
                        for collection in collections:
                            if collection.name == collection_name:
                                if collection.is_visible != initial_collection['is_visible']:
                                    return f'bpy.data.armatures["{armature.name}"].{attr_name}["{collection_name}"].is_visible'
                                break
            
            # Bone properties
            if 'bones' in initial_arm:
                for bone in armature.bones:
                    if bone.name in initial_arm['bones']:
                        initial_bone = initial_arm['bones'][bone.name]
                        
                        for prop, initial_val in initial_bone.items():
                            if hasattr(bone, prop):
                                current_val = getattr(bone, prop)
                                if current_val != initial_val:
                                    return f'bpy.data.armatures["{armature.name}"].bones["{bone.name}"].{prop}'
        
        # Check scenes
        for scene in bpy.data.scenes:
            scene_key = f"scenes.{scene.name}"
            if scene_key not in self._initial_state:
                continue
                
            initial_scene = self._initial_state[scene_key]
            
            # Basic scene properties
            basic_props = ['frame_current', 'frame_start', 'frame_end', 'use_gravity']
            for prop in basic_props:
                if prop in initial_scene:
                    current_val = getattr(scene, prop)
                    if not self.values_equal(current_val, initial_scene[prop]):
                        return f'bpy.data.scenes["{scene.name}"].{prop}'
            
            # Gravity vector
            if 'gravity' in initial_scene:
                if not self.values_equal(scene.gravity, initial_scene['gravity']):
                    # Check individual components
                    for i, (current, initial) in enumerate(zip(scene.gravity, initial_scene['gravity'])):
                        if not self.values_equal(current, initial):
                            return f'bpy.data.scenes["{scene.name}"].gravity[{i}]'
            
            # EEVEE properties
            if 'eevee' in initial_scene and hasattr(scene, 'eevee'):
                for prop, initial_val in initial_scene['eevee'].items():
                    if hasattr(scene.eevee, prop):
                        current_val = getattr(scene.eevee, prop)
                        if not self.values_equal(current_val, initial_val):
                            return f'bpy.data.scenes["{scene.name}"].eevee.{prop}'
            
            # Cycles properties
            if 'cycles' in initial_scene and hasattr(scene, 'cycles'):
                for prop, initial_val in initial_scene['cycles'].items():
                    if hasattr(scene.cycles, prop):
                        current_val = getattr(scene.cycles, prop)
                        if not self.values_equal(current_val, initial_val):
                            return f'bpy.data.scenes["{scene.name}"].cycles.{prop}'
        
        # Check materials
        for mat in bpy.data.materials:
            mat_key = f"materials.{mat.name}"
            if mat_key not in self._initial_state or not (mat.use_nodes and mat.node_tree):
                continue
                
            initial_mat = self._initial_state[mat_key]
            
            if 'nodes' in initial_mat:
                for node in mat.node_tree.nodes:
                    if node.name in initial_mat['nodes']:
                        initial_node = initial_mat['nodes'][node.name]
                        
                        # Check node mute
                        if 'mute' in initial_node and hasattr(node, 'mute'):
                            if node.mute != initial_node['mute']:
                                return f'bpy.data.materials["{mat.name}"].node_tree.nodes["{node.name}"].mute'
                        
                        # Check input values
                        if 'inputs' in initial_node and hasattr(node, 'inputs'):
                            for i, input_socket in enumerate(node.inputs):
                                if i in initial_node['inputs'] and hasattr(input_socket, 'default_value'):
                                    try:
                                        current_val = input_socket.default_value
                                        initial_val = initial_node['inputs'][i]
                                        
                                        if not self.values_equal(current_val, initial_val):
                                            return f'bpy.data.materials["{mat.name}"].node_tree.nodes["{node.name}"].inputs[{i}].default_value'
                                    except:
                                        pass
        
        return None


#---------------------------------------
# Constraint Operators
#---------------------------------------
class OBJECT_OT_limit_source_transforms(bpy.types.Operator):
    """Add limit constraints to source bone/object based on recorded min/max values"""
    bl_idname = "object.limit_source_transforms"
    bl_label = "Limit Source Transforms"
    bl_description = "Add limit constraints to prevent source from going beyond recorded min/max values"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.driver_recorder_props
        
        try:
            # Automatically detect source type from recorded data
            if props.from_bone:
                success = self.limit_bone_transforms(props, context)
            elif props.from_object:
                success = self.limit_object_transforms(props, context)
            else:
                self.report({'ERROR'}, "No source configured. Please record MIN and MAX first.")
                return {'CANCELLED'}
            
            if success:
                self.report({'INFO'}, "Limit constraints added successfully")
            else:
                self.report({'ERROR'}, "Failed to add limit constraints")
                
        except Exception as e:
            self.report({'ERROR'}, f"Error adding constraints: {str(e)}")
            return {'CANCELLED'}
        
        return {'FINISHED'}

    def limit_bone_transforms(self, props, context):
        """Add limit constraints to bone"""
        if not props.from_armature or not props.from_bone:
            self.report({'ERROR'}, "No source bone configured")
            return False
        
        if not (props.from_has_min and props.from_has_max and props.from_detected_axis):
            self.report({'ERROR'}, "FROM bone needs MIN, MAX, and detected axis")
            return False
        
        # Get armature and bone
        armature = bpy.data.objects.get(props.from_armature)
        if not armature or armature.type != 'ARMATURE':
            self.report({'ERROR'}, f"Armature '{props.from_armature}' not found")
            return False
        
        # Check if bone exists
        if props.from_bone not in armature.pose.bones:
            self.report({'ERROR'}, f"Bone '{props.from_bone}' not found in armature")
            return False
        
        pose_bone = armature.pose.bones[props.from_bone]
        
        # Parse detected axis
        axis_info = self.parse_axis_info(props.from_detected_axis)
        if not axis_info:
            self.report({'ERROR'}, f"Could not parse axis info: {props.from_detected_axis}")
            return False
        
        # Add appropriate constraint
        constraint_name = f"Limit_{axis_info['transform']}_{axis_info['axis']}"
        
        if axis_info['transform'] == 'LOC':
            return self.add_location_limit(pose_bone, axis_info, props.from_min_location, props.from_max_location, constraint_name)
        elif axis_info['transform'] == 'ROT':
            return self.add_rotation_limit(pose_bone, axis_info, props.from_min_rotation, props.from_max_rotation, constraint_name)
        elif axis_info['transform'] == 'SCALE':
            self.report({'WARNING'}, "Scale limiting not yet implemented")
            return False
        
        return False

    def limit_object_transforms(self, props, context):
        """Add limit constraints to object"""
        if not props.from_object:
            self.report({'ERROR'}, "No source object configured")
            return False
        
        if not (props.from_object_has_min and props.from_object_has_max and props.from_object_detected_axis):
            self.report({'ERROR'}, "FROM object needs MIN, MAX, and detected axis")
            return False
        
        # Get object
        obj = bpy.data.objects.get(props.from_object)
        if not obj:
            self.report({'ERROR'}, f"Object '{props.from_object}' not found")
            return False
        
        # Parse detected axis
        axis_info = self.parse_axis_info(props.from_object_detected_axis)
        if not axis_info:
            self.report({'ERROR'}, f"Could not parse axis info: {props.from_object_detected_axis}")
            return False
        
        # Add appropriate constraint
        constraint_name = f"Limit_{axis_info['transform']}_{axis_info['axis']}"
        
        if axis_info['transform'] == 'LOC':
            return self.add_object_location_limit(obj, axis_info, props.from_object_min_location, props.from_object_max_location, constraint_name)
        elif axis_info['transform'] == 'ROT':
            return self.add_object_rotation_limit(obj, axis_info, props.from_object_min_rotation, props.from_object_max_rotation, constraint_name)
        elif axis_info['transform'] == 'SCALE':
            self.report({'WARNING'}, "Scale limiting not yet implemented for objects")
            return False
        
        return False

    def parse_axis_info(self, axis_string):
        """Parse axis string like 'LOC X' or 'ROT Y' into components"""
        if not axis_string:
            return None
        
        parts = axis_string.split()
        if len(parts) != 2:
            return None
        
        transform_type = parts[0]  # LOC, ROT, SCALE
        axis = parts[1]  # X, Y, Z
        
        # Map axis to index
        axis_map = {'X': 0, 'Y': 1, 'Z': 2}
        if axis not in axis_map:
            return None
        
        return {
            'transform': transform_type,
            'axis': axis,
            'index': axis_map[axis]
        }

    def get_sorted_values(self, min_val, max_val):
        """Ensure min is actually smaller than max, swap if needed"""
        if min_val > max_val:
            return max_val, min_val  # Swap them
        return min_val, max_val

    def add_location_limit(self, pose_bone, axis_info, min_loc, max_loc, constraint_name):
        """Add location limit constraint to pose bone"""
        # Remove existing constraint with same name
        if constraint_name in pose_bone.constraints:
            pose_bone.constraints.remove(pose_bone.constraints[constraint_name])
        
        # Add limit location constraint
        constraint = pose_bone.constraints.new('LIMIT_LOCATION')
        constraint.name = constraint_name
        
        axis_idx = axis_info['index']
        
        # Get properly sorted min/max values
        actual_min, actual_max = self.get_sorted_values(min_loc[axis_idx], max_loc[axis_idx])
        
        # Set limits for the specific axis
        if axis_info['axis'] == 'X':
            constraint.use_min_x = True
            constraint.use_max_x = True
            constraint.min_x = actual_min
            constraint.max_x = actual_max
        elif axis_info['axis'] == 'Y':
            constraint.use_min_y = True
            constraint.use_max_y = True
            constraint.min_y = actual_min
            constraint.max_y = actual_max
        elif axis_info['axis'] == 'Z':
            constraint.use_min_z = True
            constraint.use_max_z = True
            constraint.min_z = actual_min
            constraint.max_z = actual_max
        
        constraint.owner_space = 'LOCAL'
        
        # Debug info
        print(f"Added location limit to {pose_bone.name} {axis_info['axis']}: {actual_min:.3f} to {actual_max:.3f}")
        return True

    def add_rotation_limit(self, pose_bone, axis_info, min_rot, max_rot, constraint_name):
        """Add rotation limit constraint to pose bone"""
        # Remove existing constraint with same name
        if constraint_name in pose_bone.constraints:
            pose_bone.constraints.remove(pose_bone.constraints[constraint_name])
        
        # Use Euler angles for constraint computation only; avoid permanently changing mode
        original_mode = pose_bone.rotation_mode
        if original_mode == 'QUATERNION':
            temp_euler = pose_bone.rotation_quaternion.to_euler('XYZ')
            pose_bone.rotation_mode = 'XYZ'
            pose_bone.rotation_euler = temp_euler
        
        # Add limit rotation constraint
        constraint = pose_bone.constraints.new('LIMIT_ROTATION')
        constraint.name = constraint_name
        
        axis_idx = axis_info['index']
        
        # Get properly sorted min/max values (in radians)
        actual_min_rad, actual_max_rad = self.get_sorted_values(min_rot[axis_idx], max_rot[axis_idx])
        
        # Convert radians to degrees for the constraint
        actual_min_deg = math.degrees(actual_min_rad)
        actual_max_deg = math.degrees(actual_max_rad)
        
        # Set limits for the specific axis
        if axis_info['axis'] == 'X':
            constraint.use_limit_x = True
            constraint.min_x = math.radians(actual_min_deg)
            constraint.max_x = math.radians(actual_max_deg)
        elif axis_info['axis'] == 'Y':
            constraint.use_limit_y = True
            constraint.min_y = math.radians(actual_min_deg)
            constraint.max_y = math.radians(actual_max_deg)
        elif axis_info['axis'] == 'Z':
            constraint.use_limit_z = True
            constraint.min_z = math.radians(actual_min_deg)
            constraint.max_z = math.radians(actual_max_deg)
        
        # Set constraint properties for proper rotation handling
        constraint.owner_space = 'LOCAL'
        constraint.use_transform_limit = True
        
        # Debug info
        print(f"Added rotation limit to {pose_bone.name} {axis_info['axis']}: {actual_min_deg:.1f}° to {actual_max_deg:.1f}°")
        return True

    def add_object_location_limit(self, obj, axis_info, min_loc, max_loc, constraint_name):
        """Add location limit constraint to object"""
        # Remove existing constraint with same name
        for constraint in obj.constraints:
            if constraint.name == constraint_name:
                obj.constraints.remove(constraint)
                break
        
        # Add limit location constraint
        constraint = obj.constraints.new('LIMIT_LOCATION')
        constraint.name = constraint_name
        
        axis_idx = axis_info['index']
        
        # Get properly sorted min/max values
        actual_min, actual_max = self.get_sorted_values(min_loc[axis_idx], max_loc[axis_idx])
        
        # Set limits for the specific axis
        if axis_info['axis'] == 'X':
            constraint.use_min_x = True
            constraint.use_max_x = True
            constraint.min_x = actual_min
            constraint.max_x = actual_max
        elif axis_info['axis'] == 'Y':
            constraint.use_min_y = True
            constraint.use_max_y = True
            constraint.min_y = actual_min
            constraint.max_y = actual_max
        elif axis_info['axis'] == 'Z':
            constraint.use_min_z = True
            constraint.use_max_z = True
            constraint.min_z = actual_min
            constraint.max_z = actual_max
        
        # Debug info
        print(f"Added location limit to {obj.name} {axis_info['axis']}: {actual_min:.3f} to {actual_max:.3f}")
        return True

    def add_object_rotation_limit(self, obj, axis_info, min_rot, max_rot, constraint_name):
        """Add rotation limit constraint to object"""
        # Remove existing constraint with same name
        for constraint in obj.constraints:
            if constraint.name == constraint_name:
                obj.constraints.remove(constraint)
                break
        
        # Force object to use Euler rotation mode
        obj.rotation_mode = 'XYZ'
        
        # Add limit rotation constraint
        constraint = obj.constraints.new('LIMIT_ROTATION')
        constraint.name = constraint_name
        
        axis_idx = axis_info['index']
        
        # Get properly sorted min/max values (in radians)
        actual_min_rad, actual_max_rad = self.get_sorted_values(min_rot[axis_idx], max_rot[axis_idx])
        
        # Convert radians to degrees for the constraint
        actual_min_deg = math.degrees(actual_min_rad)
        actual_max_deg = math.degrees(actual_max_rad)
        
        # Set limits for the specific axis - Blender rotation constraints use RADIANS
        if axis_info['axis'] == 'X':
            constraint.use_limit_x = True
            constraint.min_x = actual_min_rad
            constraint.max_x = actual_max_rad
        elif axis_info['axis'] == 'Y':
            constraint.use_limit_y = True
            constraint.min_y = actual_min_rad
            constraint.max_y = actual_max_rad
        elif axis_info['axis'] == 'Z':
            constraint.use_limit_z = True
            constraint.min_z = actual_min_rad
            constraint.max_z = actual_max_rad
        
        # Set constraint properties for proper rotation handling
        constraint.use_transform_limit = True
        
        # Debug info
        print(f"Added rotation limit to {obj.name} {axis_info['axis']}: {actual_min_deg:.1f}° to {actual_max_deg:.1f}°")
        return True

class OBJECT_OT_one_axis_source_limit(bpy.types.Operator):
    """Lock source to move/rotate only on the detected axis, preventing movement on other axes"""
    bl_idname = "object.one_axis_source_limit"
    bl_label = "Lock to One Axis Only"
    bl_description = "Lock source to only move/rotate on the detected axis, blocking all other axes"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.driver_recorder_props
        
        try:
            # Automatically detect source type from recorded data
            if props.from_bone:
                success = self.lock_bone_to_axis(props, context)
            elif props.from_object:
                success = self.lock_object_to_axis(props, context)
            else:
                self.report({'ERROR'}, "No source configured. Please record MIN and MAX first.")
                return {'CANCELLED'}
            
            if success:
                self.report({'INFO'}, "One-axis constraint added successfully")
            else:
                self.report({'ERROR'}, "Failed to add one-axis constraint")
                
        except Exception as e:
            self.report({'ERROR'}, f"Error adding one-axis constraint: {str(e)}")
            return {'CANCELLED'}
        
        return {'FINISHED'}

    def lock_bone_to_axis(self, props, context):
        """Add constraints to lock bone to single axis movement"""
        if not props.from_armature or not props.from_bone:
            self.report({'ERROR'}, "No source bone configured")
            return False
        
        if not (props.from_has_min and props.from_has_max and props.from_detected_axis):
            self.report({'ERROR'}, "FROM bone needs MIN, MAX, and detected axis")
            return False
        
        # Get armature and bone
        armature = bpy.data.objects.get(props.from_armature)
        if not armature or armature.type != 'ARMATURE':
            self.report({'ERROR'}, f"Armature '{props.from_armature}' not found")
            return False
        
        if props.from_bone not in armature.pose.bones:
            self.report({'ERROR'}, f"Bone '{props.from_bone}' not found in armature")
            return False
        
        pose_bone = armature.pose.bones[props.from_bone]
        
        # Parse detected axis
        axis_info = self.parse_axis_info(props.from_detected_axis)
        if not axis_info:
            self.report({'ERROR'}, f"Could not parse axis info: {props.from_detected_axis}")
            return False
        
        if axis_info['transform'] == 'LOC':
            return self.add_bone_location_lock(pose_bone, axis_info, props.from_min_location, props.from_max_location)
        elif axis_info['transform'] == 'ROT':
            return self.add_bone_rotation_lock(pose_bone, axis_info, props.from_min_rotation, props.from_max_rotation)
        elif axis_info['transform'] == 'SCALE':
            self.report({'WARNING'}, "Scale locking not yet implemented")
            return False
        
        return False

    def lock_object_to_axis(self, props, context):
        """Add constraints to lock object to single axis movement"""
        if not props.from_object:
            self.report({'ERROR'}, "No source object configured")
            return False
        
        if not (props.from_object_has_min and props.from_object_has_max and props.from_object_detected_axis):
            self.report({'ERROR'}, "FROM object needs MIN, MAX, and detected axis")
            return False
        
        obj = bpy.data.objects.get(props.from_object)
        if not obj:
            self.report({'ERROR'}, f"Object '{props.from_object}' not found")
            return False
        
        # Parse detected axis
        axis_info = self.parse_axis_info(props.from_object_detected_axis)
        if not axis_info:
            self.report({'ERROR'}, f"Could not parse axis info: {props.from_object_detected_axis}")
            return False
        
        if axis_info['transform'] == 'LOC':
            return self.add_object_location_lock(obj, axis_info, props.from_object_min_location, props.from_object_max_location)
        elif axis_info['transform'] == 'ROT':
            return self.add_object_rotation_lock(obj, axis_info, props.from_object_min_rotation, props.from_object_max_rotation)
        elif axis_info['transform'] == 'SCALE':
            self.report({'WARNING'}, "Scale locking not yet implemented for objects")
            return False
        
        return False

    def parse_axis_info(self, axis_string):
        """Parse axis string like 'LOC X' or 'ROT Y' into components"""
        if not axis_string:
            return None
        
        parts = axis_string.split()
        if len(parts) != 2:
            return None
        
        transform_type = parts[0]  # LOC, ROT, SCALE
        axis = parts[1]  # X, Y, Z
        
        axis_map = {'X': 0, 'Y': 1, 'Z': 2}
        if axis not in axis_map:
            return None
        
        return {
            'transform': transform_type,
            'axis': axis,
            'index': axis_map[axis]
        }

    def get_sorted_values(self, min_val, max_val):
        """Ensure min is actually smaller than max"""
        if min_val > max_val:
            return max_val, min_val
        return min_val, max_val

    def add_bone_location_lock(self, pose_bone, axis_info, min_loc, max_loc):
        """Lock bone location to only the detected axis"""
        constraint_name = f"OneAxis_LOC_{axis_info['axis']}"
        
        # Remove existing constraint
        if constraint_name in pose_bone.constraints:
            pose_bone.constraints.remove(pose_bone.constraints[constraint_name])
        
        # Add limit location constraint that locks OTHER axes
        constraint = pose_bone.constraints.new('LIMIT_LOCATION')
        constraint.name = constraint_name
        constraint.owner_space = 'LOCAL'
        
        # Get current position to use as lock point for other axes
        current_loc = pose_bone.location.copy()
        
        # Get sorted min/max for the active axis
        axis_idx = axis_info['index']
        actual_min, actual_max = self.get_sorted_values(min_loc[axis_idx], max_loc[axis_idx])
        
        # Lock all axes except the detected one
        if axis_info['axis'] != 'X':
            # Lock X axis to current position
            constraint.use_min_x = True
            constraint.use_max_x = True
            constraint.min_x = current_loc[0]
            constraint.max_x = current_loc[0]
        else:
            # Allow X axis movement within recorded range
            constraint.use_min_x = True
            constraint.use_max_x = True
            constraint.min_x = actual_min
            constraint.max_x = actual_max
        
        if axis_info['axis'] != 'Y':
            # Lock Y axis to current position
            constraint.use_min_y = True
            constraint.use_max_y = True
            constraint.min_y = current_loc[1]
            constraint.max_y = current_loc[1]
        else:
            # Allow Y axis movement within recorded range
            constraint.use_min_y = True
            constraint.use_max_y = True
            constraint.min_y = actual_min
            constraint.max_y = actual_max
        
        if axis_info['axis'] != 'Z':
            # Lock Z axis to current position
            constraint.use_min_z = True
            constraint.use_max_z = True
            constraint.min_z = current_loc[2]
            constraint.max_z = current_loc[2]
        else:
            # Allow Z axis movement within recorded range
            constraint.use_min_z = True
            constraint.use_max_z = True
            constraint.min_z = actual_min
            constraint.max_z = actual_max
        
        print(f"Locked {pose_bone.name} to {axis_info['axis']} axis only (range: {actual_min:.3f} to {actual_max:.3f})")
        return True

    def add_bone_rotation_lock(self, pose_bone, axis_info, min_rot, max_rot):
        """Lock bone rotation to only the detected axis"""
        constraint_name = f"OneAxis_ROT_{axis_info['axis']}"
        
        # Remove existing constraint
        if constraint_name in pose_bone.constraints:
            pose_bone.constraints.remove(pose_bone.constraints[constraint_name])
        
        # Force bone to use Euler rotation mode
        pose_bone.rotation_mode = 'XYZ'
        
        # Add limit rotation constraint that locks OTHER axes
        constraint = pose_bone.constraints.new('LIMIT_ROTATION')
        constraint.name = constraint_name
        constraint.owner_space = 'LOCAL'
        constraint.use_transform_limit = True
        
        # Get current rotation to use as lock point for other axes
        current_rot = pose_bone.rotation_euler.copy()
        
        # Get sorted min/max for the active axis (in radians)
        axis_idx = axis_info['index']
        actual_min_rad, actual_max_rad = self.get_sorted_values(min_rot[axis_idx], max_rot[axis_idx])
        
        # Lock all axes except the detected one
        if axis_info['axis'] != 'X':
            # Lock X rotation to current position
            constraint.use_limit_x = True
            constraint.min_x = current_rot[0]
            constraint.max_x = current_rot[0]
        else:
            # Allow X rotation within recorded range
            constraint.use_limit_x = True
            constraint.min_x = actual_min_rad
            constraint.max_x = actual_max_rad
        
        if axis_info['axis'] != 'Y':
            # Lock Y rotation to current position
            constraint.use_limit_y = True
            constraint.min_y = current_rot[1]
            constraint.max_y = current_rot[1]
        else:
            # Allow Y rotation within recorded range
            constraint.use_limit_y = True
            constraint.min_y = actual_min_rad
            constraint.max_y = actual_max_rad
        
        if axis_info['axis'] != 'Z':
            # Lock Z rotation to current position
            constraint.use_limit_z = True
            constraint.min_z = current_rot[2]
            constraint.max_z = current_rot[2]
        else:
            # Allow Z rotation within recorded range
            constraint.use_limit_z = True
            constraint.min_z = actual_min_rad
            constraint.max_z = actual_max_rad
        
        actual_min_deg = math.degrees(actual_min_rad)
        actual_max_deg = math.degrees(actual_max_rad)
        print(f"Locked {pose_bone.name} to {axis_info['axis']} rotation only (range: {actual_min_deg:.1f}° to {actual_max_deg:.1f}°)")
        return True

    def add_object_location_lock(self, obj, axis_info, min_loc, max_loc):
        """Lock object location to only the detected axis"""
        constraint_name = f"OneAxis_LOC_{axis_info['axis']}"
        
        # Remove existing constraint
        for constraint in obj.constraints:
            if constraint.name == constraint_name:
                obj.constraints.remove(constraint)
                break
        
        # Add limit location constraint
        constraint = obj.constraints.new('LIMIT_LOCATION')
        constraint.name = constraint_name
        
        # Get current position
        current_loc = obj.location.copy()
        
        # Get sorted min/max for the active axis
        axis_idx = axis_info['index']
        actual_min, actual_max = self.get_sorted_values(min_loc[axis_idx], max_loc[axis_idx])
        
        # Lock all axes except the detected one
        if axis_info['axis'] != 'X':
            constraint.use_min_x = True
            constraint.use_max_x = True
            constraint.min_x = current_loc[0]
            constraint.max_x = current_loc[0]
        else:
            constraint.use_min_x = True
            constraint.use_max_x = True
            constraint.min_x = actual_min
            constraint.max_x = actual_max
        
        if axis_info['axis'] != 'Y':
            constraint.use_min_y = True
            constraint.use_max_y = True
            constraint.min_y = current_loc[1]
            constraint.max_y = current_loc[1]
        else:
            constraint.use_min_y = True
            constraint.use_max_y = True
            constraint.min_y = actual_min
            constraint.max_y = actual_max
        
        if axis_info['axis'] != 'Z':
            constraint.use_min_z = True
            constraint.use_max_z = True
            constraint.min_z = current_loc[2]
            constraint.max_z = current_loc[2]
        else:
            constraint.use_min_z = True
            constraint.use_max_z = True
            constraint.min_z = actual_min
            constraint.max_z = actual_max
        
        print(f"Locked {obj.name} to {axis_info['axis']} axis only (range: {actual_min:.3f} to {actual_max:.3f})")
        return True

    def add_object_rotation_lock(self, obj, axis_info, min_rot, max_rot):
        """Lock object rotation to only the detected axis"""
        constraint_name = f"OneAxis_ROT_{axis_info['axis']}"
        
        # Remove existing constraint
        for constraint in obj.constraints:
            if constraint.name == constraint_name:
                obj.constraints.remove(constraint)
                break
        
        # Force object to use Euler rotation mode
        obj.rotation_mode = 'XYZ'
        
        # Add limit rotation constraint
        constraint = obj.constraints.new('LIMIT_ROTATION')
        constraint.name = constraint_name
        constraint.use_transform_limit = True
        
        # Get current rotation
        current_rot = obj.rotation_euler.copy()
        
        # Get sorted min/max for the active axis (in radians)
        axis_idx = axis_info['index']
        actual_min_rad, actual_max_rad = self.get_sorted_values(min_rot[axis_idx], max_rot[axis_idx])
        
        # Lock all axes except the detected one
        if axis_info['axis'] != 'X':
            constraint.use_limit_x = True
            constraint.min_x = current_rot[0]
            constraint.max_x = current_rot[0]
        else:
            constraint.use_limit_x = True
            constraint.min_x = actual_min_rad
            constraint.max_x = actual_max_rad
        
        if axis_info['axis'] != 'Y':
            constraint.use_limit_y = True
            constraint.min_y = current_rot[1]
            constraint.max_y = current_rot[1]
        else:
            constraint.use_limit_y = True
            constraint.min_y = actual_min_rad
            constraint.max_y = actual_max_rad
        
        if axis_info['axis'] != 'Z':
            constraint.use_limit_z = True
            constraint.min_z = current_rot[2]
            constraint.max_z = current_rot[2]
        else:
            constraint.use_limit_z = True
            constraint.min_z = actual_min_rad
            constraint.max_z = actual_max_rad
        
        actual_min_deg = math.degrees(actual_min_rad)
        actual_max_deg = math.degrees(actual_max_rad)
        print(f"Locked {obj.name} to {axis_info['axis']} rotation only (range: {actual_min_deg:.1f}° to {actual_max_deg:.1f}°)")
        return True

#---------------------------------------
# Fine Tuning Operators
#---------------------------------------
class ANIM_OT_toggle_fine_tune(bpy.types.Operator):
    bl_idname = "anim.toggle_fine_tune"
    bl_label = "Toggle Fine Tune"
    bl_description = "Toggle fine tune mode for manual adjustment"

    def execute(self, context):
        props = context.scene.driver_recorder_props
        
        # Toggle fine tune mode
        context.scene.source_fine_tune_mode = not context.scene.source_fine_tune_mode
        
        # If we're turning it on, initialize fine tune values based on recorded data
        if context.scene.source_fine_tune_mode:
            if props.from_bone:
                self.init_bone_fine_tune(props)
            elif props.from_object:
                self.init_object_fine_tune(props)
        
        return {'FINISHED'}
    
    def init_bone_fine_tune(self, props):
        """Initialize fine tune values for bone."""
        # Get current axis and values
        detected_axis = props.from_detected_axis
        
        # Set axis dropdown
        axis_map = {
            "LOC X": "LOC_X", "LOC Y": "LOC_Y", "LOC Z": "LOC_Z",
            "ROT X": "ROT_X", "ROT Y": "ROT_Y", "ROT Z": "ROT_Z"
        }
        props.fine_tune_axis = axis_map.get(detected_axis, "LOC_X")
        
        # Get min/max values based on axis
        if "LOC" in detected_axis:
            axis_idx = ["X", "Y", "Z"].index(detected_axis.split()[-1])
            props.fine_tune_min_value = props.from_min_location[axis_idx]
            props.fine_tune_max_value = props.from_max_location[axis_idx]
        elif "ROT" in detected_axis:
            axis_idx = ["X", "Y", "Z"].index(detected_axis.split()[-1])
            props.fine_tune_min_value = props.from_min_rotation[axis_idx]
            props.fine_tune_max_value = props.from_max_rotation[axis_idx]
    
    def init_object_fine_tune(self, props):
        """Initialize fine tune values for object."""
        # Get current axis and values
        detected_axis = props.from_object_detected_axis
        
        # Set axis dropdown
        axis_map = {
            "LOC X": "LOC_X", "LOC Y": "LOC_Y", "LOC Z": "LOC_Z",
            "ROT X": "ROT_X", "ROT Y": "ROT_Y", "ROT Z": "ROT_Z"
        }
        props.fine_tune_object_axis = axis_map.get(detected_axis, "LOC_X")
        
        # Get min/max values based on axis
        if "LOC" in detected_axis:
            axis_idx = ["X", "Y", "Z"].index(detected_axis.split()[-1])
            props.fine_tune_object_min_value = props.from_object_min_location[axis_idx]
            props.fine_tune_object_max_value = props.from_object_max_location[axis_idx]
        elif "ROT" in detected_axis:
            axis_idx = ["X", "Y", "Z"].index(detected_axis.split()[-1])
            props.fine_tune_object_min_value = props.from_object_min_rotation[axis_idx]
            props.fine_tune_object_max_value = props.from_object_max_rotation[axis_idx]

class ANIM_OT_close_fine_tune(bpy.types.Operator):
    bl_idname = "anim.close_fine_tune"
    bl_label = "Close Fine Tune"
    bl_description = "Close fine tune mode"

    def execute(self, context):
        context.scene.source_fine_tune_mode = False
        return {'FINISHED'}

#---------------------------------------
# Source>Recording Operators
#---------------------------------------
class ANIM_OT_record_from_min(bpy.types.Operator):
    bl_idname = "anim.record_from_min"
    bl_label = "Record Min Position"
    bl_description = "Record the current position/rotation as minimum (auto-detects bone/object mode)"

    def execute(self, context):
        props = context.scene.driver_recorder_props
        obj = context.object
        
        if not obj:
            self.report({'ERROR'}, "Please select an object")
            return {'CANCELLED'}
        
        # Close fine tune mode when recording new values
        context.scene.source_fine_tune_mode = False
        
        # Auto-detect mode based on context
        if obj.type == 'ARMATURE' and obj.mode == 'POSE':
            return self.record_bone_min(context, props, obj)
        else:
            return self.record_object_min(context, props, obj)
    
    def record_bone_min(self, context, props, obj):
        """Record bone minimum values."""
        bone = context.active_pose_bone
        if not bone:
            self.report({'ERROR'}, "No active bone selected")
            return {'CANCELLED'}
        
        # Clear any existing object data
        self.clear_object_data(props)
        
        # Set as FROM bone and record min
        props.from_armature = obj.name
        props.from_bone = bone.name
        props.from_min_location = bone.location[:]
        euler = ensure_euler_rotation(bone)
        props.from_min_rotation = (euler.x, euler.y, euler.z)
        props.from_has_min = True
        
        # Clear max and detected axis since we have a new bone
        props.from_has_max = False
        props.from_detected_axis = ""
        
        self.report({'INFO'}, f"Recorded MIN for bone {bone.name}")
        return {'FINISHED'}
    
    def record_object_min(self, context, props, obj):
        """Record object minimum values."""
        # Clear any existing bone data
        self.clear_bone_data(props)
        
        # Set as FROM object and record min
        props.from_object = obj.name
        props.from_object_min_location = obj.location[:]
        euler = ensure_object_euler_rotation(obj)
        props.from_object_min_rotation = (euler.x, euler.y, euler.z)
        props.from_object_has_min = True
        
        # Clear max and detected axis since we have a new object
        props.from_object_has_max = False
        props.from_object_detected_axis = ""
        
        self.report({'INFO'}, f"Recorded MIN for object {obj.name}")
        return {'FINISHED'}
    
    def clear_bone_data(self, props):
        """Clear all bone-related data."""
        props.from_armature = ""
        props.from_bone = ""
        props.from_has_min = False
        props.from_has_max = False
        props.from_detected_axis = ""
    
    def clear_object_data(self, props):
        """Clear all object-related data."""
        props.from_object = ""
        props.from_object_has_min = False
        props.from_object_has_max = False
        props.from_object_detected_axis = ""

class ANIM_OT_record_from_max(bpy.types.Operator):
    bl_idname = "anim.record_from_max"
    bl_label = "Record Max Position"
    bl_description = "Record the current position/rotation as maximum and detect primary axis"

    def execute(self, context):
        props = context.scene.driver_recorder_props
        obj = context.object
        
        if not obj:
            self.report({'ERROR'}, "Please select an object")
            return {'CANCELLED'}
        
        # Close fine tune mode when recording new values
        context.scene.source_fine_tune_mode = False
        
        # Determine mode based on what was recorded for min
        if props.from_bone:
            return self.record_bone_max(context, props, obj)
        elif props.from_object:
            return self.record_object_max(context, props, obj)
        else:
            self.report({'ERROR'}, "Please record MIN position first")
            return {'CANCELLED'}
    
    def record_bone_max(self, context, props, obj):
        """Record bone maximum values."""
        if not props.from_has_min or not props.from_bone:
            self.report({'ERROR'}, "Please record MIN position first")
            return {'CANCELLED'}
        
        if not obj or obj.name != props.from_armature or obj.type != 'ARMATURE' or obj.mode != 'POSE':
            self.report({'ERROR'}, "Please select the same armature in Pose Mode")
            return {'CANCELLED'}
        
        bone = obj.pose.bones.get(props.from_bone)
        if not bone:
            self.report({'ERROR'}, "FROM bone not found")
            return {'CANCELLED'}
        
        # Record max values
        props.from_max_location = bone.location[:]
        euler = ensure_euler_rotation(bone)
        props.from_max_rotation = (euler.x, euler.y, euler.z)
        props.from_has_max = True
        
        # Detect primary axis
        self.detect_bone_axis(props)
        
        self.report({'INFO'}, f"Detected: {props.from_detected_axis}")
        return {'FINISHED'}
    
    def record_object_max(self, context, props, obj):
        """Record object maximum values."""
        if not props.from_object_has_min or not props.from_object:
            self.report({'ERROR'}, "Please record MIN position first")
            return {'CANCELLED'}
        
        if not obj or obj.name != props.from_object:
            self.report({'ERROR'}, "Please select the same object")
            return {'CANCELLED'}
        
        # Record max values
        props.from_object_max_location = obj.location[:]
        euler = ensure_object_euler_rotation(obj)
        props.from_object_max_rotation = (euler.x, euler.y, euler.z)
        props.from_object_has_max = True
        
        # Detect primary axis
        self.detect_object_axis(props)
        
        self.report({'INFO'}, f"Detected: {props.from_object_detected_axis}")
        return {'FINISHED'}
    
    def detect_bone_axis(self, props):
        """Detect primary axis for bone transforms."""
        min_vals = {
            'location': props.from_min_location,
            'rotation': props.from_min_rotation
        }
        max_vals = {
            'location': props.from_max_location,
            'rotation': props.from_max_rotation
        }
        
        changes = detect_significant_changes(min_vals, max_vals)
        
        if changes:
            # Find the change with the largest difference
            largest_change = max(changes, key=lambda x: abs(x[3] - x[2]))
            transform_type, axis, _, _ = largest_change
            
            axis_names = ['X', 'Y', 'Z']
            if transform_type == 'location':
                props.from_detected_axis = f"LOC {axis_names[axis]}"
            else:
                props.from_detected_axis = f"ROT {axis_names[axis]}"
        else:
            props.from_detected_axis = "No significant change detected"
    
    def detect_object_axis(self, props):
        """Detect primary axis for object transforms."""
        min_vals = {
            'location': props.from_object_min_location,
            'rotation': props.from_object_min_rotation
        }
        max_vals = {
            'location': props.from_object_max_location,
            'rotation': props.from_object_max_rotation
        }
        
        changes = detect_significant_changes(min_vals, max_vals)
        
        if changes:
            # Find the change with the largest difference
            largest_change = max(changes, key=lambda x: abs(x[3] - x[2]))
            transform_type, axis, _, _ = largest_change
            
            axis_names = ['X', 'Y', 'Z']
            if transform_type == 'location':
                props.from_object_detected_axis = f"LOC {axis_names[axis]}"
            else:
                props.from_object_detected_axis = f"ROT {axis_names[axis]}"
        else:
            props.from_object_detected_axis = "No significant change detected"

#---------------------------------------
# Target>Pose Operators
#---------------------------------------
class POSE_OT_remove_pose_bone(bpy.types.Operator):
    bl_idname = "pose.remove_pose_bone"
    bl_label = "Remove Pose Bone"
    bl_description = "Remove this bone from the target list"
   
    bone_name: bpy.props.StringProperty()
    
    def execute(self, context):
        props = context.scene.driver_recorder_props
        to_data = get_to_bones_data(props)
        
        if self.bone_name in to_data:
            del to_data[self.bone_name]
            set_to_bones_data(props, to_data)
            self.report({'INFO'}, f"Removed bone: {self.bone_name}")
        else:
            self.report({'WARNING'}, f"Bone not found: {self.bone_name}")
        
        return {'FINISHED'}

class POSE_OT_record_to_min_pose(bpy.types.Operator):
    bl_idname = "pose.record_to_min_pose"
    bl_label = "Record MIN Pose"
    bl_description = "Record current pose as minimum for all selected bones"

    def execute(self, context):
        props = context.scene.driver_recorder_props
        obj, selected_bones = get_selected_pose_bones(context)
        
        if not obj or not selected_bones:
            self.report({'ERROR'}, "Please select bones in Pose Mode")
            return {'CANCELLED'}
        
        to_data = get_to_bones_data(props)
        
        for bone in selected_bones:
            ensure_euler_rotation(bone, True)
            
            bone_data = to_data.get(bone.name, {
                'armature': obj.name,
                'has_min': False,
                'has_max': False,
                'min_location': [0, 0, 0],
                'max_location': [0, 0, 0],
                'min_rotation': [0, 0, 0],
                'max_rotation': [0, 0, 0],
                'detected_changes': []
            })
            
            bone_data['min_location'] = list(bone.location)
            bone_data['min_rotation'] = list(ensure_euler_rotation(bone, True))
            bone_data['has_min'] = True
            bone_data['has_max'] = False  # Reset max when recording new min
            bone_data['detected_changes'] = []  # Reset changes
            
            to_data[bone.name] = bone_data
        
        set_to_bones_data(props, to_data)
        
        self.report({'INFO'}, f"Recorded MIN pose for {len(selected_bones)} bones")
        return {'FINISHED'}

class POSE_OT_record_to_max_pose(bpy.types.Operator):
    bl_idname = "pose.record_to_max_pose"
    bl_label = "Record MAX Pose"
    bl_description = "Record current pose as maximum and detect changes for all target bones"

    def execute(self, context):
        props = context.scene.driver_recorder_props
        obj, selected_bones = get_selected_pose_bones(context)
        
        if not obj or not selected_bones:
            self.report({'ERROR'}, "Please select bones in Pose Mode")
            return {'CANCELLED'}
        
        to_data = get_to_bones_data(props)
        bones_processed = 0
        
        for bone in selected_bones:
            if bone.name in to_data and to_data[bone.name]['has_min']:
                ensure_euler_rotation(bone, True)
                bone_data = to_data[bone.name]
                
                # Record max values
                bone_data['max_location'] = list(bone.location)
                bone_data['max_rotation'] = list(ensure_euler_rotation(bone, True))
                bone_data['has_max'] = True
                
                # Detect changes
                min_vals = {
                    'location': bone_data['min_location'],
                    'rotation': bone_data['min_rotation']
                }
                max_vals = {
                    'location': bone_data['max_location'],
                    'rotation': bone_data['max_rotation']
                }
                
                changes = detect_significant_changes(min_vals, max_vals)
                bone_data['detected_changes'] = []
                
                for transform_type, axis, min_val, max_val in changes:
                    axis_names = ['X', 'Y', 'Z']
                    if transform_type == 'location':
                        change_str = f"LOC {axis_names[axis]}"
                    else:
                        change_str = f"ROT {axis_names[axis]}"
                    
                    bone_data['detected_changes'].append({
                        'type': transform_type,
                        'axis': axis,
                        'display': change_str,
                        'min_val': min_val,
                        'max_val': max_val
                    })
                
                bones_processed += 1
        
        set_to_bones_data(props, to_data)
        
        self.report({'INFO'}, f"Recorded MAX pose for {bones_processed} bones")
        return {'FINISHED'}

#---------------------------------------
# Target>Shapekey Operators
#---------------------------------------
class MESH_OT_add_shapekey_target(bpy.types.Operator):
    bl_idname = "mesh.add_shapekey_target"
    bl_label = "Add Shape Key"
    bl_description = "Add the selected shape key to the target list"

    def execute(self, context):
        props = context.scene.driver_recorder_props
        
        if not props.shapekey_target_object or not props.shapekey_name:
            self.report({'ERROR'}, "Please select an object and shape key")
            return {'CANCELLED'}
        
        # Validate object exists and has shape keys
        obj = bpy.data.objects.get(props.shapekey_target_object)
        if not obj:
            self.report({'ERROR'}, "Selected object not found")
            return {'CANCELLED'}
        
        if not (obj.data and hasattr(obj.data, 'shape_keys') and obj.data.shape_keys):
            self.report({'ERROR'}, "Selected object has no shape keys")
            return {'CANCELLED'}
        
        # Validate shape key exists
        key_block = obj.data.shape_keys.key_blocks.get(props.shapekey_name)
        if not key_block:
            self.report({'ERROR'}, "Selected shape key not found")
            return {'CANCELLED'}
        
        shapekey_data = get_shapekey_list_data(props)
        
        # Create unique key for this shapekey
        key = f"{props.shapekey_target_object}:{props.shapekey_name}"
        
        # Check if already exists
        if key in shapekey_data:
            self.report({'WARNING'}, f"Shape key {props.shapekey_name} from {props.shapekey_target_object} already exists")
            return {'CANCELLED'}
        
        shapekey_data[key] = {
            'object': props.shapekey_target_object,
            'shapekey': props.shapekey_name,
            'min_value': props.shapekey_min_value,
            'max_value': props.shapekey_max_value
        }
        
        set_shapekey_list_data(props, shapekey_data)
        
        # Reset the shape key value to zero
        key_block.value = 0.0
        
        # Clear inputs after adding
        props.shapekey_target_object = ""
        props.shapekey_name = ""
        props.shapekey_min_value = 0.0
        props.shapekey_max_value = 1.0
        
        self.report({'INFO'}, f"Added {props.shapekey_name} from {props.shapekey_target_object} (reset to 0.0)")
        return {'FINISHED'}


class MESH_OT_edit_shapekey_target(bpy.types.Operator):
    bl_idname = "mesh.edit_shapekey_target"
    bl_label = "Edit Shape Key"
    bl_description = "Edit this shape key (loads values into inputs and removes from list)"

    key_to_edit: bpy.props.StringProperty()

    def execute(self, context):
        props = context.scene.driver_recorder_props
        shapekey_data = get_shapekey_list_data(props)
        
        if self.key_to_edit not in shapekey_data:
            self.report({'ERROR'}, "Shape key not found in list")
            return {'CANCELLED'}
        
        # Get the data
        sk_data = shapekey_data[self.key_to_edit]
        
        # Load values into inputs
        props.shapekey_target_object = sk_data['object']
        props.shapekey_name = sk_data['shapekey']
        props.shapekey_min_value = sk_data['min_value']
        props.shapekey_max_value = sk_data['max_value']
        
        # Remove from list
        del shapekey_data[self.key_to_edit]
        set_shapekey_list_data(props, shapekey_data)
        
        self.report({'INFO'}, f"Loaded {sk_data['shapekey']} from {sk_data['object']} for editing")
        return {'FINISHED'}

class MESH_OT_remove_shapekey_target(bpy.types.Operator):
    bl_idname = "mesh.remove_shapekey_target"
    bl_label = "Remove"
    bl_description = "Remove this shape key from the list"

    key_to_remove: bpy.props.StringProperty()

    def execute(self, context):
        props = context.scene.driver_recorder_props
        shapekey_data = get_shapekey_list_data(props)
        
        if self.key_to_remove in shapekey_data:
            sk_data = shapekey_data[self.key_to_remove]
            del shapekey_data[self.key_to_remove]
            set_shapekey_list_data(props, shapekey_data)
            self.report({'INFO'}, f"Removed {sk_data['shapekey']} from {sk_data['object']}")
        else:
            self.report({'ERROR'}, "Shape key not found in list")
        
        return {'FINISHED'}

#---------------------------------------
# Target>Path Operators
#---------------------------------------
class SCENE_OT_validate_path(bpy.types.Operator):
    bl_idname = "scene.validate_path"
    bl_label = "Validate Path"
    bl_description = "Test if the custom path is valid and accessible"

    def execute(self, context):
        props = context.scene.driver_recorder_props
        
        if not props.custom_path_input:
            self.report({'ERROR'}, "Please enter a path to validate")
            return {'CANCELLED'}
        
        is_valid, result = validate_custom_path(props.custom_path_input)
        
        if is_valid:
            self.report({'INFO'}, f"Valid path! Type: {result}")
        else:
            self.report({'ERROR'}, f"Invalid path: {result}")
        
        return {'FINISHED'}

class SCENE_OT_add_path_target(bpy.types.Operator):
    bl_idname = "scene.add_path_target"
    bl_label = "Add Path"
    bl_description = "Add the custom path to the target list"

    def execute(self, context):
        props = context.scene.driver_recorder_props
        
        if not props.custom_path_input:
            self.report({'ERROR'}, "Please enter a custom path")
            return {'CANCELLED'}
        
        # Parse the path to get data block, data path, and index
        data_block, data_path, index = parse_target_path(props.custom_path_input)
        
        if data_block is None or data_path is None:
            self.report({'ERROR'}, "Invalid or unsupported path format")
            return {'CANCELLED'}
        
        # Auto-detect the property type using the parsed components
        detected_type = auto_detect_path_type(data_block, data_path, index)
        
        path_data = get_path_list_data(props)
        
        # Create unique key for this path
        key = props.custom_path_input
        
        # Check if already exists
        if key in path_data:
            self.report({'WARNING'}, f"Path already exists in list")
            return {'CANCELLED'}
        
        # Use the detected type but manual values from UI
        if detected_type == 'FLOAT':
            path_data[key] = {
                'path': props.custom_path_input,
                'type': 'FLOAT',
                'min_value': props.path_min_value,
                'max_value': props.path_max_value
            }
        else:  # BOOLEAN
            path_data[key] = {
                'path': props.custom_path_input,
                'type': 'BOOLEAN',
                'false_value': props.path_false_value,
                'true_value': props.path_true_value
            }
        
        set_path_list_data(props, path_data)
        
        # Clear inputs after adding
        props.custom_path_input = ""
        props.path_min_value = 0.0
        props.path_max_value = 1.0
        props.path_false_value = 0.0
        props.path_true_value = 1.0
        
        # Report what was detected and added
        type_text = "boolean" if detected_type == 'BOOLEAN' else "float"
        self.report({'INFO'}, f"Added {type_text} path")
        
        return {'FINISHED'}

class SCENE_OT_edit_path_target(bpy.types.Operator):
    bl_idname = "scene.edit_path_target"
    bl_label = "Edit Path"
    bl_description = "Edit this path (loads values into inputs and removes from list)"
    
    key_to_edit: bpy.props.StringProperty()

    def execute(self, context):
        props = context.scene.driver_recorder_props
        path_data = get_path_list_data(props)
        
        if self.key_to_edit not in path_data:
            self.report({'ERROR'}, "Path not found in list")
            return {'CANCELLED'}
        
        # Get the data
        path_info = path_data[self.key_to_edit]
        
        # Load values into inputs
        props.custom_path_input = path_info['path']
        
        if path_info['type'] == 'FLOAT':
            props.path_min_value = path_info['min_value']
            props.path_max_value = path_info['max_value']
            # Reset boolean values to defaults
            props.path_false_value = 0.0
            props.path_true_value = 1.0
        else:  # BOOLEAN
            props.path_false_value = path_info['false_value']
            props.path_true_value = path_info['true_value']
            # Reset float values to defaults
            props.path_min_value = 0.0
            props.path_max_value = 1.0
        
        # Remove from list
        del path_data[self.key_to_edit]
        set_path_list_data(props, path_data)
        
        type_text = "boolean" if path_info['type'] == 'BOOLEAN' else "float"
        self.report({'INFO'}, f"Loaded {type_text} path for editing")
        return {'FINISHED'}

class SCENE_OT_remove_path_target(bpy.types.Operator):
    bl_idname = "scene.remove_path_target"
    bl_label = "Remove"
    bl_description = "Remove this path from the list"
   
    key_to_remove: bpy.props.StringProperty()

    def execute(self, context):
        props = context.scene.driver_recorder_props
        path_data = get_path_list_data(props)
        
        if self.key_to_remove in path_data:
            path_info = path_data[self.key_to_remove]
            del path_data[self.key_to_remove]
            set_path_list_data(props, path_data)
            
            # Show shortened path in message
            display_path = self.key_to_remove if len(self.key_to_remove) <= 40 else self.key_to_remove[:37] + "..."
            self.report({'INFO'}, f"Removed path: {display_path}")
        else:
            self.report({'ERROR'}, "Path not found in list")
        
        return {'FINISHED'}

#---------------------------------------
# Actions>Driver&Expression Operators
#---------------------------------------
class ANIM_OT_create_drivers(bpy.types.Operator):
    bl_idname = "anim.create_drivers"
    bl_label = "Create Drivers"
    bl_description = "Create drivers from FROM source to all targets"

    def execute(self, context):
        props = context.scene.driver_recorder_props
        
        # Initialize variables
        from_path = None
        source_name = None
        from_min = None
        from_max = None
        
        # Automatically detect source type and validate
        if props.from_bone:
            # Using bone source
            if not (props.from_has_min and props.from_has_max and props.from_detected_axis):
                self.report({'ERROR'}, "FROM bone needs MIN, MAX, and detected axis")
                return {'CANCELLED'}
            
            # Get FROM bone values
            from_axis_type, from_axis_name = props.from_detected_axis.split(' ')
            from_axis_index = ['X', 'Y', 'Z'].index(from_axis_name)
            
            if from_axis_type == 'LOC':
                from_min = props.from_min_location[from_axis_index]
                from_max = props.from_max_location[from_axis_index]
                from_prop = 'location'
            else:  # ROT
                from_min = props.from_min_rotation[from_axis_index]
                from_max = props.from_max_rotation[from_axis_index]
                from_prop = 'rotation_euler'
            
            from_path = f"{props.from_armature}.pose.bones[\"{props.from_bone}\"].{from_prop}[{from_axis_index}]"
            source_name = props.from_armature
            
        elif props.from_object:
            # Using object source
            if not (props.from_object_has_min and props.from_object_has_max and props.from_object_detected_axis):
                self.report({'ERROR'}, "FROM object needs MIN, MAX, and detected axis")
                return {'CANCELLED'}
            
            # Get FROM object values
            from_axis_type, from_axis_name = props.from_object_detected_axis.split(' ')
            from_axis_index = ['X', 'Y', 'Z'].index(from_axis_name)
            
            if from_axis_type == 'LOC':
                from_min = props.from_object_min_location[from_axis_index]
                from_max = props.from_object_max_location[from_axis_index]
                from_prop = 'location'
            else:  # ROT
                from_min = props.from_object_min_rotation[from_axis_index]
                from_max = props.from_object_max_rotation[from_axis_index]
                from_prop = 'rotation_euler'
            
            from_path = f"{props.from_object}.{from_prop}[{from_axis_index}]"
            source_name = props.from_object
            
        else:
            self.report({'ERROR'}, "No source configured. Please record MIN and MAX first.")
            return {'CANCELLED'}
        
        # Validate that we have all required source data
        if not all([from_path, source_name, from_min is not None, from_max is not None]):
            self.report({'ERROR'}, "Failed to configure source data")
            return {'CANCELLED'}
        
        drivers_created = 0
        
        if props.target_type == 'CUSTOM_POSE':
            # Create drivers for custom pose bones
            to_data = get_to_bones_data(props)
            if not to_data:
                self.report({'ERROR'}, "No TO bones recorded")
                return {'CANCELLED'}
            
            for bone_name, bone_data in to_data.items():
                if not (bone_data.get('has_min', False) and bone_data.get('has_max', False)):
                    print(f"Skipping bone {bone_name}: missing min/max data")
                    continue
                
                detected_changes = bone_data.get('detected_changes', [])
                if not detected_changes:
                    print(f"Skipping bone {bone_name}: no detected changes")
                    continue
                
                for change in detected_changes:
                    try:
                        to_prop = change.get('type')
                        to_axis = change.get('axis')
                        to_min = change.get('min_val')
                        to_max = change.get('max_val')
                        armature_name = bone_data.get('armature')
                        
                        # Validate all required data is present
                        if None in [to_prop, to_axis, to_min, to_max, armature_name]:
                            print(f"Skipping change for {bone_name}: missing data - prop:{to_prop}, axis:{to_axis}, min:{to_min}, max:{to_max}, armature:{armature_name}")
                            continue
                        
                        to_path = f"{armature_name}.pose.bones[\"{bone_name}\"].{to_prop}[{to_axis}]"
                        
                        print(f"Creating driver: {bone_name} - {to_prop}[{to_axis}]")
                        
                        success = createDriver(
                            armature_name=source_name,
                            from_path=from_path,
                            fromMin=from_min,
                            fromMax=from_max,
                            to_path=to_path,
                            toMin=to_min,
                            toMax=to_max,
                            selfRotation=False,
                            isDegrees=False
                        )
                        
                        if success:
                            drivers_created += 1
                            print(f"✓ Driver created successfully")
                        else:
                            print(f"✗ Driver creation failed")
                            
                    except Exception as e:
                        print(f"Error processing change for bone {bone_name}: {e}")
                        continue
        
        elif props.target_type == 'SHAPEKEY_LIST':
            # Create drivers for shape keys
            shapekey_data = get_shapekey_list_data(props)
            if not shapekey_data:
                self.report({'ERROR'}, "No shape keys in list")
                return {'CANCELLED'}
            
            for key, sk_data in shapekey_data.items():
                try:
                    to_path = f"{sk_data['object']}.data.shape_keys.key_blocks[\"{sk_data['shapekey']}\"].value"
                    
                    success = createDriver(
                        armature_name=source_name,
                        from_path=from_path,
                        fromMin=from_min,
                        fromMax=from_max,
                        to_path=to_path,
                        toMin=sk_data['min_value'],
                        toMax=sk_data['max_value'],
                        selfRotation=False,
                        isDegrees=False
                    )
                    
                    if success:
                        drivers_created += 1
                        
                except Exception as e:
                    print(f"Error creating shapekey driver for {key}: {e}")
                    continue
        
        elif props.target_type == 'PATH_LIST':
            # Create drivers for custom paths
            path_data = get_path_list_data(props)
            if not path_data:
                self.report({'ERROR'}, "No custom paths in list")
                return {'CANCELLED'}
            
            for path, path_info in path_data.items():
                try:
                    if path_info['type'] == 'FLOAT':
                        to_min = path_info['min_value']
                        to_max = path_info['max_value']
                    else:  # BOOLEAN
                        to_min = path_info['false_value']
                        to_max = path_info['true_value']
                    
                    success = createDriver(
                        armature_name=source_name,
                        from_path=from_path,
                        fromMin=from_min,
                        fromMax=from_max,
                        to_path=path,  # path is already the full path here
                        toMin=to_min,
                        toMax=to_max,
                        selfRotation=False,
                        isDegrees=False
                    )
                    
                    if success:
                        drivers_created += 1
                        
                except Exception as e:
                    print(f"Error creating path driver for {path}: {e}")
                    continue
        
        self.report({'INFO'}, f"Created {drivers_created} drivers")
        return {'FINISHED'}

class ANIM_OT_remove_drivers(bpy.types.Operator):
    bl_idname = "anim.remove_drivers"
    bl_label = "Remove Drivers"
    bl_description = "Remove all drivers from targets and selected objects"

    def execute(self, context):
        props = context.scene.driver_recorder_props
        
        # Automatically detect source type and validate
        if props.from_bone:
            if not props.from_bone:
                self.report({'ERROR'}, "No FROM bone set")
                return {'CANCELLED'}
        elif props.from_object:
            if not props.from_object:
                self.report({'ERROR'}, "No FROM object set")
                return {'CANCELLED'}
        else:
            self.report({'ERROR'}, "No source configured")
            return {'CANCELLED'}
        
        drivers_removed = 0
        
        # Remove drivers from configured targets
        if props.target_type == 'CUSTOM_POSE':
            to_data = get_to_bones_data(props)
            
            for bone_name, bone_data in to_data.items():
                armature = bpy.data.objects.get(bone_data['armature'])
                if not armature or not armature.animation_data:
                    continue
                
                # Remove drivers for this bone
                for change in bone_data.get('detected_changes', []):
                    to_prop = change['type']
                    to_axis = change['axis']
                    data_path = f'pose.bones["{bone_name}"].{to_prop}'
                    
                    try:
                        armature.driver_remove(data_path, to_axis)
                        drivers_removed += 1
                    except:
                        pass
        
        elif props.target_type == 'SHAPEKEY_LIST':
            shapekey_data = get_shapekey_list_data(props)
            
            for key, sk_data in shapekey_data.items():
                obj = bpy.data.objects.get(sk_data['object'])
                if not obj or not obj.data or not hasattr(obj.data, 'shape_keys'):
                    continue
                
                data_path = f'key_blocks["{sk_data["shapekey"]}"].value'
                
                try:
                    obj.data.shape_keys.driver_remove(data_path)
                    drivers_removed += 1
                except:
                    pass
        
        elif props.target_type == 'PATH_LIST':
            path_data = get_path_list_data(props)
            
            for path, path_info in path_data.items():
                # Extract object and data path from custom path
                if path.startswith('bpy.data.objects["'):
                    obj_match = re.match(r'bpy\.data\.objects\["([^"]+)"\]\.(.+)', path)
                    if obj_match:
                        obj_name, data_path = obj_match.groups()
                        obj = bpy.data.objects.get(obj_name)
                        if obj:
                            try:
                                # Handle array indices in data path
                                if '[' in data_path and ']' in data_path:
                                    base_path = re.sub(r'\[\d+\]', '', data_path)
                                    index_match = re.search(r'\[(\d+)\]', data_path)
                                    if index_match:
                                        index = int(index_match.group(1))
                                        obj.driver_remove(base_path, index)
                                    else:
                                        obj.driver_remove(data_path)
                                else:
                                    obj.driver_remove(data_path)
                                drivers_removed += 1
                            except:
                                pass
        
        # Remove drivers from ALL selected objects
        selected_objects = context.selected_objects
        for obj in selected_objects:
            if not obj.animation_data:
                continue
                
            # Collect all drivers to remove (to avoid modifying collection while iterating)
            drivers_to_remove = []
            
            if obj.animation_data.drivers:
                for driver in obj.animation_data.drivers:
                    drivers_to_remove.append((driver.data_path, driver.array_index))
            
            # Remove all drivers from this object
            for data_path, array_index in drivers_to_remove:
                try:
                    if array_index >= 0:
                        obj.driver_remove(data_path, array_index)
                    else:
                        obj.driver_remove(data_path)
                    drivers_removed += 1
                except:
                    pass
            
            # Also remove drivers from shape keys if they exist
            if hasattr(obj.data, 'shape_keys') and obj.data.shape_keys and obj.data.shape_keys.animation_data:
                shape_drivers_to_remove = []
                if obj.data.shape_keys.animation_data.drivers:
                    for driver in obj.data.shape_keys.animation_data.drivers:
                        shape_drivers_to_remove.append((driver.data_path, driver.array_index))
                
                for data_path, array_index in shape_drivers_to_remove:
                    try:
                        if array_index >= 0:
                            obj.data.shape_keys.driver_remove(data_path, array_index)
                        else:
                            obj.data.shape_keys.driver_remove(data_path)
                        drivers_removed += 1
                    except:
                        pass
        
        self.report({'INFO'}, f"Removed {drivers_removed} drivers from targets and selected objects")
        return {'FINISHED'}


# Add these operator classes to operators.py

class ANIM_OT_mirror_source(bpy.types.Operator):
    """Mirror source bone/object to opposite side"""
    bl_idname = "anim.mirror_source"
    bl_label = "Mirror Source"
    bl_description = "Mirror source to opposite side (keeps recorded min/max values)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.driver_recorder_props
        
        try:
            success, message = mirror_source(props)
            
            if success:
                self.report({'INFO'}, message)
            else:
                self.report({'WARNING'}, message)
                
        except Exception as e:
            self.report({'ERROR'}, f"Mirror failed: {str(e)}")
            return {'CANCELLED'}
        
        return {'FINISHED'}

class ANIM_OT_mirror_targets(bpy.types.Operator):
    """Mirror target configuration to opposite side"""
    bl_idname = "anim.mirror_targets"
    bl_label = "Mirror Targets"
    bl_description = "Mirror all targets to opposite side"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.driver_recorder_props
        
        try:
            if props.target_type == 'CUSTOM_POSE':
                success, message = mirror_pose_targets(props)
            elif props.target_type == 'SHAPEKEY_LIST':
                success, message = mirror_shapekey_targets(props)
            elif props.target_type == 'PATH_LIST':
                self.report({'INFO'}, "Mirror not supported for custom paths")
                return {'FINISHED'}
            else:
                self.report({'ERROR'}, "Unknown target type")
                return {'CANCELLED'}
            
            if success:
                self.report({'INFO'}, message)
            else:
                self.report({'WARNING'}, message)
                
        except Exception as e:
            self.report({'ERROR'}, f"Mirror failed: {str(e)}")
            return {'CANCELLED'}
        
        return {'FINISHED'}



class SCENE_OT_clear_all(bpy.types.Operator):
    bl_idname = "scene.clear_all"
    bl_label = "Clear All"
    bl_description = "Clear all recorded data"

    def execute(self, context):
        props = context.scene.driver_recorder_props
        
        # Clear bone data
        props.from_armature = ""
        props.from_bone = ""
        props.from_has_min = False
        props.from_has_max = False
        props.from_detected_axis = ""
        
        # Clear object data
        props.from_object = ""
        props.from_object_has_min = False
        props.from_object_has_max = False
        props.from_object_detected_axis = ""
        
        # Clear target data
        props.to_bones_data = "{}"
        props.shapekey_list_data = "{}"
        props.path_list_data = "{}"
        props.shapekey_target_object = ""
        props.shapekey_name = ""
        props.custom_path_input = ""
        
        self.report({'INFO'}, "All data cleared")
        return {'FINISHED'}

class SCENE_OT_set_target_type(bpy.types.Operator):
    bl_idname = "scene.set_target_type"
    bl_label = "Set Target Type"
    bl_description = "Set the target type"
  
    target_type: bpy.props.StringProperty()

    def execute(self, context):
        props = context.scene.driver_recorder_props
        props.target_type = self.target_type
        return {'FINISHED'}

class SCENE_OT_clear_source(bpy.types.Operator):
    """Clear all source configuration"""
    bl_idname = "scene.clear_source"
    bl_label = "Clear Source"
    bl_options = {'REGISTER', 'UNDO'}
  
    def execute(self, context):
        props = context.scene.driver_recorder_props
        
        # Clear bone source data
        props.from_bone = ""
        props.from_has_min = False
        props.from_has_max = False
        props.from_detected_axis = ""
        props.from_min_rotation = (0.0, 0.0, 0.0)
        props.from_max_rotation = (0.0, 0.0, 0.0)
        props.from_min_location = (0.0, 0.0, 0.0)
        props.from_max_location = (0.0, 0.0, 0.0)
        props.from_min_scale = (1.0, 1.0, 1.0)
        props.from_max_scale = (1.0, 1.0, 1.0)
        
        # Clear object source data
        props.from_object = ""
        props.from_object_has_min = False
        props.from_object_has_max = False
        props.from_object_detected_axis = ""
        props.from_object_min_rotation = (0.0, 0.0, 0.0)
        props.from_object_max_rotation = (0.0, 0.0, 0.0)
        props.from_object_min_location = (0.0, 0.0, 0.0)
        props.from_object_max_location = (0.0, 0.0, 0.0)
        props.from_object_min_scale = (1.0, 1.0, 1.0)
        props.from_object_max_scale = (1.0, 1.0, 1.0)
        
        self.report({'INFO'}, "Source configuration cleared")
        return {'FINISHED'}

class SCENE_OT_clear_targets(bpy.types.Operator):
    """Clear all target configuration"""
    bl_idname = "scene.clear_targets"
    bl_label = "Clear Targets"
    bl_options = {'REGISTER', 'UNDO'}
  
    def execute(self, context):
        props = context.scene.driver_recorder_props
        
        # Clear pose targets
        props.to_bones_data = ""
        
        # Clear shapekey targets
        props.shapekey_list_data = ""
        props.shapekey_target_object = ""
        props.shapekey_name = ""
        props.shapekey_min_value = 0.0
        props.shapekey_max_value = 1.0
        
        # Clear path targets
        props.path_list_data = ""
        props.custom_path_input = ""
        props.path_min_value = 0.0
        props.path_max_value = 1.0
        props.path_false_value = 0.0
        props.path_true_value = 1.0
        
        self.report({'INFO'}, "Target configuration cleared")
        return {'FINISHED'}

#---------------------------------------
# Registration - Dont forget to update!
#---------------------------------------
 
classes = (
    DriverRecorderProperties,
    ANIM_OT_record_from_min,
    ANIM_OT_record_from_max,
    POSE_OT_record_to_min_pose,
    POSE_OT_record_to_max_pose,
    MESH_OT_add_shapekey_target,
    MESH_OT_remove_shapekey_target,
    SCENE_OT_validate_path,
    SCENE_OT_add_path_target,
    SCENE_OT_remove_path_target,
    ANIM_OT_create_drivers,
    ANIM_OT_remove_drivers,
    SCENE_OT_clear_all,
    SCENE_OT_set_target_type,
    SCENE_OT_clear_targets,
    SCENE_OT_clear_source,
    OBJECT_OT_limit_source_transforms,
    OBJECT_OT_one_axis_source_limit,
    ANIM_OT_path_eyedropper,
    ANIM_OT_object_eyedropper,
    POSE_OT_remove_pose_bone,
    ANIM_OT_toggle_fine_tune,
    MESH_OT_edit_shapekey_target,
    SCENE_OT_edit_path_target,
    ANIM_OT_mirror_source,
    ANIM_OT_mirror_targets,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
