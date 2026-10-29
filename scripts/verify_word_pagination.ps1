# Manual M6.6 acceptance on an installed Windows PC with Microsoft Word.
# Open only a synthetic ReportMaker-generated DOCX. No network, no Save,
# no macros, no printer/export, and no report text/paths in printed results.
param(
    [Parameter(Mandatory = $true)]
    [string] $DocxPath,
    [ValidateRange(0, 100000)]
    [int] $ExpectedWordPages = 0,
    [ValidateRange(0, 100000)]
    [int] $PdfPagesForComparison = 0
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$source = (Resolve-Path -LiteralPath $DocxPath -ErrorAction Stop).ProviderPath
if ([System.IO.Path]::GetExtension($source) -ine ".docx") {
    throw "The Microsoft Word pagination check accepts a generated .docx file only"
}

$word = $null
$document = $null
try {
    try {
        $word = New-Object -ComObject Word.Application -ErrorAction Stop
    }
    catch {
        throw "Microsoft Word COM is unavailable. Run this only on Windows with desktop Word installed; automated CI cannot certify Word pagination."
    }
    $word.Visible = $false
    $word.DisplayAlerts = 0
    # Office msoAutomationSecurityForceDisable: do not run document macros.
    $word.AutomationSecurity = 3
    $word.Options.UpdateLinksAtOpen = $false
    # Documents.Open(FileName, ConfirmConversions, ReadOnly, AddToRecentFiles)
    $document = $word.Documents.Open($source, $false, $true, $false)
    $document.Repaginate()
    $before = [int] $document.ComputeStatistics(2) # wdStatisticPages

    # Update live body and header/footer fields *in memory only*.
    # The source document is opened read-only and never saved.
    [void] $document.Fields.Update()
    foreach ($section in $document.Sections) {
        foreach ($header in $section.Headers) {
            if ($header.Exists) { [void] $header.Range.Fields.Update() }
        }
        foreach ($footer in $section.Footers) {
            if ($footer.Exists) { [void] $footer.Range.Fields.Update() }
        }
    }
    $document.Repaginate()
    [void] $document.Fields.Update()
    $document.Repaginate()
    $pages = [int] $document.ComputeStatistics(2)
    if ($pages -lt 1) {
        throw "Word returned an invalid physical page count"
    }

    $referenceCount = 0
    $unresolved = 0
    foreach ($field in $document.Fields) {
        $fieldCode = [string] $field.Code.Text
        if ($fieldCode -match '(?i)\bPAGEREF\b') {
            $referenceCount++
            # Word may display localized error text rather than the '?' used
            # in our exported DOCX placeholder. Check the actual bookmark
            # target as well as the cached field result.
            $match = [regex]::Match($fieldCode,
                '(?i)\bPAGEREF\s+([A-Za-z_][A-Za-z0-9_]*)')
            if (-not $match.Success) {
                $unresolved++
                continue
            }
            $targetBookmark = $match.Groups[1].Value
            $fieldResult = [string] $field.Result.Text
            if ((-not $document.Bookmarks.Exists($targetBookmark)) -or
                [string]::IsNullOrWhiteSpace($fieldResult) -or
                $fieldResult.Trim() -match '^(\?+|Error!)') {
                $unresolved++
            }
        }
    }
    $result = [ordered] @{
        check = "native_microsoft_word_read_only_pagination"
        word_version = [string] $word.Version
        pages_before_field_update = $before
        pages_after_field_update = $pages
        page_reference_fields = $referenceCount
        unresolved_page_references = $unresolved
        expected_word_pages = $ExpectedWordPages
        pdf_pages_for_information_only = $PdfPagesForComparison
        word_pdf_pages_equal = $(if ($PdfPagesForComparison -gt 0) {
            $pages -eq $PdfPagesForComparison
        } else { $null })
    }
    # No customer/report text, document paths, or account names are emitted.
    $result | ConvertTo-Json -Compress
    if ($unresolved -ne 0) {
        throw "Word could not resolve all ReportMaker PAGEREF fields"
    }
    if ($ExpectedWordPages -gt 0 -and $pages -ne $ExpectedWordPages) {
        throw "Microsoft Word page count differs from the explicitly approved Word baseline"
    }
    # Word/PDF pagination *may* legitimately differ. Never fail just because
    # a PDF proof has a different number of pages from Microsoft Word.
}
finally {
    if ($null -ne $document) {
        try { $document.Close(0) } finally {
            [void] [Runtime.InteropServices.Marshal]::FinalReleaseComObject($document)
        }
    }
    if ($null -ne $word) {
        try { $word.Quit() } finally {
            [void] [Runtime.InteropServices.Marshal]::FinalReleaseComObject($word)
        }
    }
}
