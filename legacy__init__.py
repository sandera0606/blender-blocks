bl_info = {
    "name": "LEGO Toolkit",
    "description": "",
    "author": "sandra",
    "version": (1,0),
    "blender":(3, 0, 0),
    "location": "View3D",
    "category": "Add Mesh",
}

import bpy

############### UI PANELS ####################
class LegoToolkit_MainPanel(bpy.types.Panel):
    
    bl_label = ""
    bl_idname = "LegoToolkit_MainPanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "LEGO Toolkit"
    
    def draw_header(self, context):
        layout = self.layout
        row = layout.row()
        row.label(text="LEGO Toolkit", icon = 'AUTO')
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        row = layout.row()
        row.label(text = "Start by adding a LEGO block!")

class AddBlock_SubPanel(bpy.types.Panel):
    bl_label = "Block Library"
    bl_idname = "AddBlock_SubPanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Set Material'
    bl_parent_id = "LegoToolkit_MainPanel"
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        mytool = scene.my_tool
        row = layout.row()

#Set material dropdown

class SetMaterial_SubPanel(bpy.types.Panel):
    bl_label = "Set Material"
    bl_idname = "SetMaterial_SubPanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Set Material'
    bl_parent_id = "LegoToolkit_MainPanel"
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        ob = context.active_object
        mat = context.object.active_material

        row = layout.row()
        
        #From source code
        row.template_ID(ob, "active_material", new="material.new")
            
        #My code
        row = layout.row()
        row.label(text = "Select block type:")
        row = layout.row()
        
        c1 = row.column()
        c2 = row.column()
        
        #enable/disable buttons if no material is selected
        if(ob.active_material):
            c1.enabled, c2.enabled = True, True
        else:
            c1.enabled, c2.enabled = False, False

        #opaque, clear
        c1.operator("lego.set_opaque")
        c2.operator("lego.set_clear")
        
        
        row = layout.row()
        row.label(text = "Colour:")
        if(ob.active_material):
            layout.prop(mat, "diffuse_color", text="")
        else:
            row = layout.row()
            row.label(text = "Select a material to get started")
        

############## OPERATORS ##################

class LEGO_OT_SetOpaque(bpy.types.Operator):
    bl_label = "Opaque"
    bl_idname = "lego.set_opaque"
    
    def execute(self, context):
        mat = context.object.active_material
        mat.blend_method = 'OPAQUE'
        mat.use_nodes = False
        return {'FINISHED'}

class LEGO_OT_SetClear(bpy.types.Operator):
    bl_label = "Clear"
    bl_idname = "lego.set_clear"
    
    def execute(self, context):
        mat = context.object.active_material
        mat.blend_method = 'BLEND'
        mat.use_nodes = False
        return {'FINISHED'}


#########################################

classes = [LegoToolkit_MainPanel, AddBlock_SubPanel, LEGO_OT_SetOpaque, LEGO_OT_SetClear, SetMaterial_SubPanel]


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in classes:
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()
