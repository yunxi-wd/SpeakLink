<#
SpeakLink native WPF desktop companion. Vector artwork needs no image/model downloads.
Inputs: optional PreviewPath / Pose for offline visual verification.
Output: transparent draggable window; owned services terminate with this window.
#>
param([string]$PreviewPath = '', [ValidateSet('idle','wave','jump','sleep')][string]$Pose = 'idle', [string]$VerifyPath = '')
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName PresentationFramework, PresentationCore, WindowsBase
$root = Split-Path $PSScriptRoot -Parent
$data = Join-Path $root 'data'
[void][IO.Directory]::CreateDirectory($data)
$mutex = [Threading.Mutex]::new($false, 'Local\KnowGPT.DesktopPet.v1')
$locked = $false
try { $locked = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $locked = $true }
if (-not $locked -and -not $PreviewPath) { $mutex.Dispose(); exit }
[xml]$markup = @'
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
 Title="SpeakLink · 小知" Width="300" Height="280" WindowStyle="None" AllowsTransparency="True" Background="Transparent" ResizeMode="NoResize" Topmost="True" ShowInTaskbar="False" UseLayoutRounding="True">
 <Grid x:Name="Surface">
  <Border x:Name="Bubble" VerticalAlignment="Top" Margin="16,4,16,0" Padding="14,10" Background="#FFFDF8" BorderBrush="#E3C69F" BorderThickness="1" CornerRadius="18" IsHitTestVisible="False">
   <StackPanel><TextBlock Text="小知 · 随口一说，帮你记住" Foreground="#86603F" FontWeight="SemiBold" FontSize="13" HorizontalAlignment="Center"/><TextBlock x:Name="Hint" Text="点我打开速记 · 拖动搬家" FontSize="12" Foreground="#796B76" TextAlignment="Center" TextWrapping="Wrap" Margin="0,5,0,0"/></StackPanel>
  </Border>
  <Canvas x:Name="Art" Width="300" Height="200" VerticalAlignment="Bottom" Background="Transparent" ToolTip="点击打开 SpeakLink；拖动调整位置；右键查看更多动作">
   <Ellipse Canvas.Left="64" Canvas.Top="169" Width="174" Height="17" Fill="#22000000"/>
   <Canvas x:Name="Creature" Width="300" Height="200">
    <Canvas.RenderTransform><TranslateTransform x:Name="Bounce"/></Canvas.RenderTransform>
    <Image x:Name="PetSprite" Canvas.Left="63" Canvas.Top="-8" Width="174" Height="198" Stretch="Uniform"/>
    <Canvas Visibility="Collapsed">
     <Canvas.RenderTransform><TransformGroup><RotateTransform x:Name="Tail"/><RotateTransform x:Name="Hand"/><ScaleTransform x:Name="Blink"/></TransformGroup></Canvas.RenderTransform>
    </Canvas>
   </Canvas>
   <TextBlock x:Name="Spark" Canvas.Left="235" Canvas.Top="30" Text="✦" FontSize="24" Foreground="#D4AE64"/>
  </Canvas>
 </Grid>
</Window>
'@
$window = [Windows.Markup.XamlReader]::Load([Xml.XmlNodeReader]::new($markup))
foreach ($name in 'Hint','Art','Bounce','Tail','Blink','Hand','Spark') { Set-Variable -Name $name -Value $window.FindName($name) }
# Sprite rectangles are sampled at runtime; the original transparent PNG is preserved.
$PetSprite = $window.FindName('PetSprite')
$sheet = [Windows.Media.Imaging.BitmapImage]::new()
$sheet.BeginInit()
$sheet.CacheOption = [Windows.Media.Imaging.BitmapCacheOption]::OnLoad
$sheet.UriSource = [Uri]::new((Join-Path $PSScriptRoot 'cat-sprites.png'))
$sheet.EndInit(); $sheet.Freeze()
$frames = @()
for ($i=0; $i -lt 5; $i++) {
 $x = [int][Math]::Round(@(0,0.21,0.4,0.6,0.8)[$i]*$sheet.PixelWidth)
 $right = [int][Math]::Round(@(0.21,0.4,0.6,0.8,1)[$i]*$sheet.PixelWidth)
 $rect = [Windows.Int32Rect]::new($x, [int]($sheet.PixelHeight*0.14), $right-$x, [int]($sheet.PixelHeight*0.71))
 $frame = [Windows.Media.Imaging.CroppedBitmap]::new($sheet,$rect)
 $frame.Freeze(); $frames += $frame
}
$PetSprite.Source = $frames[0]
$script:service = $null
$script:mode = $Pose
$script:actionUntil = 0.0
$script:opening = $false
$script:moved = $false
$script:nextPoll = 0.0
$script:state = ''
$clock = [Diagnostics.Stopwatch]::StartNew()
$settingsPath = Join-Path $data 'pet-settings.json'
$area = [Windows.SystemParameters]::WorkArea
$window.Left = $area.Right - $window.Width - 25
$window.Top = $area.Bottom - $window.Height - 20
if (Test-Path $settingsPath) {
 try {
  $settings = Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json
  $window.Left = [Math]::Max($area.Left, [Math]::Min([double]$settings.left, [Math]::Max($area.Left,$area.Right-$window.Width)))
  $window.Top = [Math]::Max($area.Top, [Math]::Min([double]$settings.top, [Math]::Max($area.Top,$area.Bottom-$window.Height)))
 } catch { } # An invalid saved position must not prevent startup.
}
function Set-Pose([string]$value) {
 # Select one short action; sleeping remains until the next click or action.
 $script:mode = $value
 $script:actionUntil = $clock.Elapsed.TotalSeconds + 4
 if ($value -eq 'sleep') { $Hint.Text = '休息一下… 点击即可唤醒'; $Spark.Text = 'z Z' }
 else { $Spark.Text = '✦'; $Hint.Text = '点我打开速记 · 右键更多动作' }
}
function Open-SpeakLink {
 # Start a health-check helper asynchronously so the animation never blocks.
 if ($script:opening) { return }
 Set-Pose 'wave'
 if ($script:service -and -not $script:service.HasExited -and $script:state -eq 'ready') {
  Start-Process 'http://127.0.0.1:13000'; return
 }
 $script:opening = $true
 $script:state = 'starting'
 $Hint.Text = '正在准备速记，第一次可能稍慢…'
 $status = Join-Path $data 'pet-status.json'
 if (Test-Path $status) { Remove-Item -LiteralPath $status }
 try {
  $script:service = Start-Process -FilePath (Join-Path $root 'runtime/python/python.exe') -ArgumentList @('-B', ('"' + (Join-Path $PSScriptRoot 'pet_service.py') + '"'), [string]$PID) -WorkingDirectory $root -WindowStyle Hidden -PassThru
 } catch {
  $script:opening = $false
  $Hint.Text = '启动失败，请检查项目是否完整'
  [void][Windows.MessageBox]::Show($_.Exception.Message, 'SpeakLink 启动提示')
 }
}
$menu = [Windows.Controls.ContextMenu]::new()
foreach ($entry in @(@('打开语音速记','open'), @('打个招呼','wave'), @('开心蹦跳','jump'), @('休息一下','sleep'), @('恢复待机','idle'), @('使用说明','help'), @('退出小知','exit'))) {
 $item = [Windows.Controls.MenuItem]::new(); $item.Header = $entry[0]; $item.Tag = $entry[1]
 $item.Add_Click({
  param($sender,$eventArgs)
  switch ($sender.Tag) {
   'open' { Open-SpeakLink }
   'help' { [Windows.MessageBox]::Show("点击小知打开 SpeakLink，拖动可搬家，右键切换动作。`n`n已运行的服务会直接复用。退出桌宠只关闭桌宠启动的服务，不影响原启动窗口。请等转写/处理完成后再退出。`n`n不会自动录音，不会设置开机自启。", '小知使用说明') }
   'exit' { $window.Close() }
   default { Set-Pose $sender.Tag }
  }
 })
 [void]$menu.Items.Add($item)
}
$Art.ContextMenu = $menu
$Art.Add_MouseLeftButtonDown({
 $script:down = [Windows.Input.Mouse]::GetPosition($window)
 $script:oldLeft = $window.Left; $script:oldTop = $window.Top
 $script:moved = $false
 [void]$Art.CaptureMouse()
})
$Art.Add_MouseMove({
 if ($Art.IsMouseCaptured -and [Windows.Input.Mouse]::LeftButton -eq 'Pressed') {
  $point = [Windows.Input.Mouse]::GetPosition($window)
  $dx = $point.X-$script:down.X; $dy = $point.Y-$script:down.Y
  if ($script:moved -or [Math]::Abs($dx)+[Math]::Abs($dy) -gt 6) {
   $script:moved = $true; $window.Left += $dx; $window.Top += $dy
  }
 }
})
$Art.Add_MouseLeftButtonUp({
 $Art.ReleaseMouseCapture()
 if (-not $script:moved) { Open-SpeakLink }
})
$timer = [Windows.Threading.DispatcherTimer]::new()
$timer.Interval = [TimeSpan]::FromMilliseconds(40)
function Update-Art([double]$t) {
 # Deterministic poses make offline previews reproducible; no downloaded assets.
 if ($script:mode -ne 'sleep' -and $t -gt $script:actionUntil -and -not $PreviewPath) { $script:mode = 'idle' }
 $Bounce.Y = [Math]::Sin($t*2)*2
 $Tail.Angle = [Math]::Sin($t*3)*8
 $Hand.Angle = 0
 $Blink.ScaleY = $(if (($t % 4.7) -gt 4.48) { 0.1 } else { 1 })
 if ($script:mode -eq 'wave') { $Hand.Angle = -80 + [Math]::Sin($t*12)*24; $Tail.Angle *= 1.5 }
 if ($script:mode -eq 'jump') { $Bounce.Y = -[Math]::Abs([Math]::Sin($t*6))*24; $Hand.Angle = -40 }
 if ($script:mode -eq 'sleep') { $Blink.ScaleY = 0.08; $Tail.Angle = [Math]::Sin($t)*2; $Bounce.Y = [Math]::Sin($t)*1.4 }
 $frameIndex = 0
 if (($t % 4.7) -gt 4.48) { $frameIndex = 1 }
 if ($script:mode -eq 'wave') { $frameIndex = 2 + ([int][Math]::Floor($t*4) % 2) }
 if ($script:mode -eq 'sleep') { $frameIndex = 4 }
 $PetSprite.Source = $frames[$frameIndex]
 $Spark.Opacity = 0.45 + [Math]::Abs([Math]::Sin($t*2))*0.55
}
$timer.Add_Tick({
 $t = $clock.Elapsed.TotalSeconds
 Update-Art $t
 if ($script:opening -and $t -ge $script:nextPoll) {
  $script:nextPoll = $t+0.7
  try {
   $statusPath = Join-Path $data 'pet-status.json'
   if (Test-Path $statusPath) {
    $record = Get-Content -LiteralPath $statusPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $script:state = $record.state
    $Hint.Text = $record.message
    if ($record.state -in @('ready','reused')) {
     $script:opening = $false
     if ($VerifyPath) { $record | ConvertTo-Json | Set-Content -LiteralPath $VerifyPath -Encoding UTF8; $window.Close(); return }
     Start-Process 'http://127.0.0.1:13000'; Set-Pose 'wave'; $Hint.Text = '速记已打开，今天想记些什么？'
    }
    if ($record.state -eq 'error') {
     $script:opening = $false; $Hint.Text = '启动遇到问题，点击重试'
     if ($VerifyPath) { $record | ConvertTo-Json | Set-Content -LiteralPath $VerifyPath -Encoding UTF8; $window.Close(); return }
     [void][Windows.MessageBox]::Show($record.message, 'SpeakLink 启动提示')
    }
   }
   if ($script:opening -and $script:service.HasExited) { $script:opening = $false; $Hint.Text = '未能启动，请查看 data/logs/pet-service.log' }
  } catch { $Hint.Text = '正在等待服务状态…' }
 }
})
$window.Add_Closed({
 $timer.Stop()
 @{left=$window.Left;top=$window.Top} | ConvertTo-Json | Set-Content -LiteralPath $settingsPath -Encoding UTF8
 if ($script:service -and -not $script:service.HasExited) { $script:service.Kill(); [void]$script:service.WaitForExit(5000) }
})
try {
 if ($PreviewPath) {
  $window.Show(); Set-Pose $Pose; Update-Art 1.25; $window.UpdateLayout()
  $bitmap = [Windows.Media.Imaging.RenderTargetBitmap]::new(300,280,96,96,[Windows.Media.PixelFormats]::Pbgra32)
  $bitmap.Render($window.Content)
  $encoder = [Windows.Media.Imaging.PngBitmapEncoder]::new(); $encoder.Frames.Add([Windows.Media.Imaging.BitmapFrame]::Create($bitmap))
  $stream = [IO.File]::Create($PreviewPath); $encoder.Save($stream); $stream.Dispose(); $window.Close()
 } else {
  if ($VerifyPath) { $window.Add_ContentRendered({ Open-SpeakLink }) }
  $timer.Start(); [void]$window.ShowDialog()
 }
} finally { if ($locked) { $mutex.ReleaseMutex() }; $mutex.Dispose() }
