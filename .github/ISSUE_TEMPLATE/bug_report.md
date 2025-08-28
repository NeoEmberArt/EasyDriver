name: "🐛 Bug Report"
description: "Report an issue or unexpected behavior in EasyDriver."
labels: ["bug"]
body:
  - type: markdown
    attributes:
      value: |
        Thanks for taking the time to report a bug!  
        Please provide as much detail as possible so I can fix it quickly.
        
  - type: input
    id: blender-version
    attributes:
      label: "Blender Version"
      description: "Which version of Blender are you using? (e.g. 4.5.0)"
      placeholder: "4.5.0"
    validations:
      required: true

  - type: input
    id: addon-version
    attributes:
      label: "EasyDriver Version"
      description: "Which version of the addon are you using?"
      placeholder: "1.0.0"
    validations:
      required: true

  - type: textarea
    id: description
    attributes:
      label: "Describe the Bug"
      description: "What happened? Please explain the issue."
      placeholder: "The addon crashes when I try to record driver max..."
    validations:
      required: true

  - type: textarea
    id: steps
    attributes:
      label: "Steps to Reproduce"
      description: "How can I reproduce the bug?"
      placeholder: |
        1. Open Blender 4.5
        2. Install EasyDriver
        3. Select a bone
        4. Click 'Record Min'
        5. See error
    validations:
      required: true

  - type: textarea
    id: expected
    attributes:
      label: "Expected Behavior"
      description: "What did you expect to happen?"
      placeholder: "The addon should have recorded the driver value without error."
      
  - type: textarea
    id: logs
    attributes:
      label: "Error Messages / Logs"
      description: "Paste any error messages from Blender's console or system console if you are able."
      render: shell
