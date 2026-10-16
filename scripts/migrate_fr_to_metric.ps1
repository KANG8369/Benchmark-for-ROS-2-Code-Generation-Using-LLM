param(
    [string]$BenchmarksRoot = (Join-Path $PSScriptRoot "..\benchmarks")
)

$ErrorActionPreference = "Stop"
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
$descriptionFiles = Get-ChildItem -LiteralPath $BenchmarksRoot -Recurse -Filter "description.yaml"

foreach ($descriptionFile in $descriptionFiles) {
    $caseRoot = $descriptionFile.Directory.FullName
    $metricPath = Join-Path $caseRoot "metric.yaml"

    if (-not (Test-Path -LiteralPath $metricPath)) {
        throw "Missing metric.yaml for $($descriptionFile.FullName)"
    }

    $description = [System.IO.File]::ReadAllText($descriptionFile.FullName)
    $newline = if ($description.Contains("`r`n")) { "`r`n" } else { "`n" }

    $functionalMarker = "functional_requirements:$newline"
    $interfacesMarker = "interfaces:"
    $functionalStart = $description.IndexOf($functionalMarker, [System.StringComparison]::Ordinal)
    $interfacesStart = $description.IndexOf(
        $interfacesMarker,
        $functionalStart + $functionalMarker.Length,
        [System.StringComparison]::Ordinal)

    if ($functionalStart -lt 0 -or $interfacesStart -lt 0) {
        throw "Expected functional_requirements followed by interfaces in $($descriptionFile.FullName)"
    }

    $intentText = $description.Substring(0, $functionalStart).TrimEnd("`r", "`n") + $newline
    $frStart = $functionalStart + $functionalMarker.Length
    $frText = $description.Substring($frStart, $interfacesStart - $frStart).TrimEnd("`r", "`n") + $newline

    $packageMatch = [regex]::Match($intentText, "(?m)^\s{2}package_name:\s*(?<name>[^\r\n#]+?)\s*$")
    if (-not $packageMatch.Success) {
        throw "Could not find intent.package_name in $($descriptionFile.FullName)"
    }

    $packageName = $packageMatch.Groups["name"].Value
    $metricText = "package_name: $packageName$newline$newline" + "metrics:$newline" + $frText

    [System.IO.File]::WriteAllText($descriptionFile.FullName, $intentText, $utf8NoBom)
    [System.IO.File]::WriteAllText($metricPath, $metricText, $utf8NoBom)

    $writtenMetric = [System.IO.File]::ReadAllText($metricPath)
    $writtenFr = $writtenMetric.Substring($writtenMetric.IndexOf("metrics:$newline") + "metrics:$newline".Length)
    if ($writtenFr -cne $frText) {
        throw "FR content changed while writing $metricPath"
    }

    Write-Output "$packageName`tFR content preserved"
}

Write-Output "Migrated $($descriptionFiles.Count) benchmark cases."
