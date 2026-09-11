$ErrorActionPreference = "Stop"
$progressPreference = 'silentlyContinue'

Write-Host "Downloading vocab.txt..."
Invoke-WebRequest -Uri "https://huggingface.co/ProsusAI/finbert/resolve/main/vocab.txt" -OutFile "d:\invest-research-agent-main\cpp\models\vocab.txt"

Write-Host "Downloading ONNX Runtime..."
Invoke-WebRequest -Uri "https://github.com/microsoft/onnxruntime/releases/download/v1.16.3/onnxruntime-win-x64-1.16.3.zip" -OutFile "onnx.zip"

Write-Host "Extracting ONNX Runtime..."
Expand-Archive -Path onnx.zip -DestinationPath "d:\invest-research-agent-main\cpp\third_party" -Force

if (Test-Path "d:\invest-research-agent-main\cpp\third_party\onnxruntime-win-x64-1.16.3") {
    Rename-Item "d:\invest-research-agent-main\cpp\third_party\onnxruntime-win-x64-1.16.3" -NewName "onnxruntime" -Force
}

Remove-Item onnx.zip
Write-Host "All downloads and extractions complete."
