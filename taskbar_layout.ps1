# Prints where the taskbar's Widgets (weather) button ends and the Start button
# begins, as "widgets_right start_left" in screen pixels, whenever it changes.
# Started by taskbar_strip.py; exits when that app (process -Owner) exits.
# Read-only: it only looks at the taskbar through UI Automation.
param([int]$Owner)
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$AE = [Windows.Automation.AutomationElement]
$tree = [Windows.Automation.TreeScope]
function Find-Id($root, $id) {
    $root.FindFirst($tree::Descendants,
        (New-Object Windows.Automation.PropertyCondition($AE::AutomationIdProperty, $id)))
}
$last = ""
$tb = $null
$start = $null
$widgets = $null
while ($true) {
    if (-not (Get-Process -Id $Owner -ErrorAction SilentlyContinue)) { exit }
    try {
        if ($tb -eq $null) {
            $tb = $AE::RootElement.FindFirst($tree::Children,
                (New-Object Windows.Automation.PropertyCondition($AE::ClassNameProperty, "Shell_TrayWnd")))
        }
        # Searching the taskbar is the slow part: do it only until both are found
        if ($start -eq $null) { $start = Find-Id $tb "StartButton" }
        if ($widgets -eq $null) { $widgets = Find-Id $tb "WidgetsButton" }
        $wr = if ($widgets) { [int]$widgets.Current.BoundingRectangle.Right } else { -1 }
        $sl = if ($start) { [int]$start.Current.BoundingRectangle.Left } else { -1 }
        $line = "$wr $sl"
    } catch {
        $tb = $null; $start = $null; $widgets = $null  # Explorer restarted: look again
        $line = "-1 -1"
    }
    if ($line -ne $last) {
        [Console]::Out.WriteLine($line)
        [Console]::Out.Flush()
        $last = $line
    }
    Start-Sleep -Milliseconds 1500
}
