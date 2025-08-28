import bpy
from .core_functions import (
    get_to_bones_data, get_shapekey_list_data, get_path_list_data
)


class BONEMINMAX_PT_main_panel(bpy.types.Panel):
    bl_label = "Easy Driver"
    bl_idname = "BONEMINMAX_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Rigging"

    def draw(self, context):
        layout = self.layout
        props = context.scene.driver_recorder_props

        # Header with clear button
        header = layout.row()
        header.label(text="Driver Creator", icon='DRIVER')
        header.operator("boneminmax.clear_all", text="", icon='TRASH')
        
        layout.separator()

        # SOURCE PANEL
        self.draw_source_panel(layout, props, context)
        
        # TARGET PANEL  
        self.draw_target_panel(layout, props, context)
        
        # ACTIONS PANEL
        self.draw_actions_panel(layout, props, context)

    def draw_source_panel(self, layout, props, context):
        """Draw simplified source configuration."""
        # Collapsible source section
        box = layout.box()
        header = box.row()
        
        # Toggle icon
        icon = "TRIA_DOWN" if getattr(context.scene, "show_source", True) else "TRIA_RIGHT"
        header.prop(context.scene, "show_source", icon=icon, icon_only=True, emboss=False)
        
        # Title and status
        header.label(text="Source", icon='EXPORT')
        
        # Status indicator
        is_ready = self.get_source_status(props)
        if is_ready:
            header.label(text="", icon='CHECKMARK')
        
        # Clear source button
        header.operator("boneminmax.clear_source", text="", icon='TRASH')
        
        if not getattr(context.scene, "show_source", True):
            return
            
        # Content
        col = box.column()
        
        # Source type tabs
        row = col.row(align=True)
        row.prop(props, "from_source_type", expand=True)
        
        col.separator(factor=0.5)
        
        if props.from_source_type == 'BONE':
            self.draw_bone_source(col, props, context)
        else:
            self.draw_object_source(col, props, context)

    def draw_target_panel(self, layout, props, context):
        """Draw simplified target configuration."""
        # Collapsible target section
        box = layout.box()
        header = box.row()
        
        # Toggle icon
        icon = "TRIA_DOWN" if getattr(context.scene, "show_targets", True) else "TRIA_RIGHT"
        header.prop(context.scene, "show_targets", icon=icon, icon_only=True, emboss=False)
        
        # Title and count
        header.label(text="Targets", icon='IMPORT')
        
        target_count = self.get_target_count(props)
        if target_count > 0:
            header.label(text=f"({target_count})")
        
        # Clear targets button
        header.operator("boneminmax.clear_targets", text="", icon='TRASH')
        
        if not getattr(context.scene, "show_targets", True):
            return
            
        # Content
        col = box.column()
        
        # Target type selection - 3 buttons side by side
        row = col.row(align=True)
        
        # Custom Pose button
        pose_btn = row.operator("boneminmax.set_target_type", text="Pose", 
                               depress=(props.target_type == 'CUSTOM_POSE'))
        pose_btn.target_type = 'CUSTOM_POSE'
        
        # Shapekey List button
        shape_btn = row.operator("boneminmax.set_target_type", text="ShapeKeys",
                                depress=(props.target_type == 'SHAPEKEY_LIST'))
        shape_btn.target_type = 'SHAPEKEY_LIST'
        
        # Path List button
        path_btn = row.operator("boneminmax.set_target_type", text="Custom Paths",
                               depress=(props.target_type == 'PATH_LIST'))
        path_btn.target_type = 'PATH_LIST'
        
        col.separator(factor=0.5)
        
        # Target-specific UI
        if props.target_type == 'CUSTOM_POSE':
            self.draw_pose_targets(col, props)
        elif props.target_type == 'SHAPEKEY_LIST':
            self.draw_shapekey_targets(col, props)
        elif props.target_type == 'PATH_LIST':
            self.draw_path_targets(col, props)

    # ... rest of the methods remain the same ...
    def draw_bone_source(self, layout, props, context):
        """Draw bone source controls."""
        # Record buttons
        row = layout.row(align=True)
        row.scale_y = 1.2
        
        min_btn = row.operator("boneminmax.record_from_min", text="Record Min")
        max_btn = row.operator("boneminmax.record_from_max", text="Record Max")
        
        # Status display
        if props.from_bone:
            layout.separator(factor=0.5)
            
            info = layout.box()
            info.scale_y = 0.9
            
            # Bone name
            row = info.row()
            row.label(text=props.from_bone, icon='BONE_DATA')
            
            # Progress indicators
            row = info.row(align=True)
            
            # Min/Max status
            min_col = row.column()
            min_col.label(text="Min", icon='KEYFRAME_HLT' if props.from_has_min else 'KEYFRAME')
            
            max_col = row.column()  
            max_col.label(text="Max", icon='KEYFRAME_HLT' if props.from_has_max else 'KEYFRAME')
            
            # Detected axis
            if props.from_detected_axis:
                axis_col = row.column()
                axis_col.label(text=props.from_detected_axis, icon='ORIENTATION_GIMBAL')

    def draw_object_source(self, layout, props, context):
        """Draw object source controls."""
        # Record buttons
        row = layout.row(align=True)
        row.scale_y = 1.2
        
        row.operator("boneminmax.record_object_min", text="Record Min")
        row.operator("boneminmax.record_object_max", text="Record Max")
        
        # Status display
        if props.from_object:
            layout.separator(factor=0.5)
            
            info = layout.box()
            info.scale_y = 0.9
            
            # Object name
            row = info.row()
            row.label(text=props.from_object, icon='OBJECT_DATA')
            
            # Progress indicators
            row = info.row(align=True)
            
            # Min/Max status
            min_col = row.column()
            min_col.label(text="Min", icon='KEYFRAME_HLT' if props.from_object_has_min else 'KEYFRAME')
            
            max_col = row.column()
            max_col.label(text="Max", icon='KEYFRAME_HLT' if props.from_object_has_max else 'KEYFRAME')
            
            # Detected axis
            if props.from_object_detected_axis:
                axis_col = row.column()
                axis_col.label(text=props.from_object_detected_axis, icon='ORIENTATION_GIMBAL')

    def draw_pose_targets(self, layout, props):
        """Draw pose target controls."""
        # Record buttons
        row = layout.row(align=True)
        row.scale_y = 1.2
        row.operator("boneminmax.record_to_min_pose", text="Record Min Pose")
        row.operator("boneminmax.record_to_max_pose", text="Record Max Pose")
        
        # Target list
        to_data = get_to_bones_data(props)
        if to_data:
            layout.separator(factor=0.5)
            
            list_box = layout.box()
            list_box.label(text="Bones:", icon='OUTLINER_DATA_ARMATURE')
            
            for bone_name, bone_data in to_data.items():
                if bone_data.get('has_min') and bone_data.get('has_max'):
                    row = list_box.row()
                    row.label(text=bone_name, icon='BONE_DATA')
                    
                    # Show changes
                    changes = bone_data.get('detected_changes', [])
                    if changes:
                        change_text = " & ".join([c['display'] for c in changes])
                        row.label(text=change_text, icon='ORIENTATION_GIMBAL')

    def draw_shapekey_targets(self, layout, props):
        """Draw shapekey target controls."""
        # Quick add section
        add_box = layout.box()
        add_box.label(text="Add Shape Key:", icon='PLUS')
        
        # Object selection
        add_box.prop_search(props, "shapekey_target_object", bpy.data, "objects", text="Object")
        
        # Shape key selection
        if props.shapekey_target_object:
            obj = bpy.data.objects.get(props.shapekey_target_object)
            if obj and obj.data and hasattr(obj.data, 'shape_keys') and obj.data.shape_keys:
                add_box.prop_search(props, "shapekey_name", obj.data.shape_keys, "key_blocks", text="Shape Key")
                
                if props.shapekey_name and props.shapekey_name != "Basis":
                    # Value range
                    row = add_box.row(align=True)
                    row.prop(props, "shapekey_min_value", text="Min")
                    row.prop(props, "shapekey_max_value", text="Max")
                    
                    # Add button
                    add_box.operator("boneminmax.add_shapekey_target", text="Add", icon='PLUS')
        
        # Target list
        shapekey_data = get_shapekey_list_data(props)
        if shapekey_data:
            layout.separator(factor=0.5)
            
            list_box = layout.box()
            list_box.label(text="Shape Keys:", icon='SHAPEKEY_DATA')
            
            for key, sk_data in shapekey_data.items():
                row = list_box.row()
                
                # Info
                col = row.column()
                col.label(text=f"{sk_data['object']}: {sk_data['shapekey']}")
                col.label(text=f"{sk_data['min_value']:.2f} → {sk_data['max_value']:.2f}")
                col.scale_y = 0.8
                
                # Remove button
                op = row.operator("boneminmax.remove_shapekey_target", text="", icon='X')
                op.key_to_remove = key

    def draw_path_targets(self, layout, props):
        """Draw custom path target controls."""
        # Quick add section
        add_box = layout.box()
        add_box.label(text="Add Custom Path:", icon='PLUS')
        
        # Path input
        add_box.prop(props, "custom_path_input", text="Path")
        
        if props.custom_path_input:
            # Validate button
            add_box.operator("boneminmax.validate_path", text="Validate", icon='CHECKMARK')
            
            # Value type and range
            add_box.prop(props, "path_value_type", text="Type")
            
            if props.path_value_type == 'FLOAT':
                row = add_box.row(align=True)
                row.prop(props, "path_min_value", text="Min")
                row.prop(props, "path_max_value", text="Max")
            else:
                row = add_box.row(align=True)
                row.prop(props, "path_false_value", text="False")
                row.prop(props, "path_true_value", text="True")
            
            # Add button
            add_box.operator("boneminmax.add_path_target", text="Add", icon='PLUS')
        
        # Target list
        path_data = get_path_list_data(props)
        if path_data:
            layout.separator(factor=0.5)
            
            list_box = layout.box()
            list_box.label(text="Custom Paths:", icon='SCRIPT')
            
            for path, path_info in path_data.items():
                row = list_box.row()
                
                # Info
                col = row.column()
                # Shortened path
                display_path = path if len(path) <= 30 else path[:27] + "..."
                col.label(text=display_path)
                
                # Value info
                if path_info['type'] == 'FLOAT':
                    col.label(text=f"{path_info['min_value']:.2f} → {path_info['max_value']:.2f}")
                else:
                    col.label(text=f"{path_info['false_value']:.2f} / {path_info['true_value']:.2f}")
                col.scale_y = 0.8
                
                # Remove button
                op = row.operator("boneminmax.remove_path_target", text="", icon='X')
                op.key_to_remove = path

    def draw_actions_panel(self, layout, props, context):
        """Draw action buttons."""
        box = layout.box()
        
        # Status check
        source_ready = self.get_source_status(props)
        target_count = self.get_target_count(props)
        can_create = source_ready and target_count > 0
        
        # Status message
        if can_create:
            box.label(text="Ready to create drivers", icon='CHECKMARK')
        else:
            box.label(text="Set up source and targets", icon='INFO')
        
        # Action buttons
        col = box.column(align=True)
        col.scale_y = 1.3
        
        # Create button
        create_row = col.row()
        create_row.enabled = bool(can_create)
        create_row.operator("boneminmax.create_drivers", text="Create Drivers", icon='PLUS')
        
        # Constraint buttons section
        col.separator(factor=0.5)
        constraint_col = col.column(align=True)
        constraint_col.scale_y = 1.0
        
        # Limit Source button
        limit_row = constraint_col.row()
        limit_row.enabled = bool(source_ready)
        limit_row.operator("boneminmax.limit_source_transforms", text="Limit Source Transforms", icon='CONSTRAINT')
        
        # One Axis Limit button
        one_axis_row = constraint_col.row()
        one_axis_row.enabled = bool(source_ready)
        one_axis_row.operator("boneminmax.one_axis_source_limit", text="Lock to One Axis Only", icon='LOCKED')
        
        col.separator(factor=0.5)
        
        # Remove button
        col.operator("boneminmax.remove_drivers", text="Remove Drivers", icon='REMOVE')



    def get_source_status(self, props):
        """Check if source is properly configured."""
        if props.from_source_type == 'BONE':
            return bool(props.from_has_min and props.from_has_max and props.from_detected_axis)
        else:
            return bool(props.from_object_has_min and props.from_object_has_max and props.from_object_detected_axis)

    def get_target_count(self, props):
        """Get number of configured targets."""
        if props.target_type == 'CUSTOM_POSE':
            to_data = get_to_bones_data(props)
            return len([b for b in to_data.values() if b.get('has_min') and b.get('has_max')])
        elif props.target_type == 'SHAPEKEY_LIST':
            return len(get_shapekey_list_data(props))
        elif props.target_type == 'PATH_LIST':
            return len(get_path_list_data(props))
        return 0


# List of UI classes for registration
classes = (
    BONEMINMAX_PT_main_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
