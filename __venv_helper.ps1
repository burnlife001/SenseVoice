# UV Pip Best Practices Menu Script

$requirementsFile = "requirements.txt"
$envName = ".venv"
$envPath = "$PSScriptRoot\$envName"

function Set-UVLinkMode {
    # Set UV link mode to copy to avoid hardlink warnings
    $env:UV_LINK_MODE = "copy"
    Write-Host "UV_LINK_MODE=copy has been set to avoid hardlink warnings" -ForegroundColor Cyan
}

function Install-UV {
    # Check if in virtual environment
    if (-not (Test-Path "$envPath\Scripts\activate")) {
        Write-Host "Please create and activate the virtual environment first!" -ForegroundColor Red
        return
    }

    # Check if virtual environment is activated
    if (-not ($env:VIRTUAL_ENV)) {
        Write-Host "Please activate the virtual environment first! Use option 8 to activate the environment." -ForegroundColor Red
        return
    }

    if (Get-Command uv -ErrorAction SilentlyContinue) {
        Write-Host "UV is already installed in the current virtual environment." -ForegroundColor Cyan
        $currentVersion = (uv --version).Trim()
        Write-Host "Current version: $currentVersion" -ForegroundColor Cyan        
        
        $updateChoice = Read-Host "Do you want to update UV to the latest version? (Y/N)"
        if ($updateChoice -eq "Y" -or $updateChoice -eq "y") {
            Write-Host "Updating UV..." -ForegroundColor Cyan
            Set-UVLinkMode
            uv pip install --upgrade uv --link-mode=copy
            Write-Host "UV has been updated." -ForegroundColor Green
            $restartChoice = Read-Host "Do you want to restart the script to apply changes? (Y/N)"
            if ($restartChoice -eq "Y" -or $restartChoice -eq "y") {
                Write-Host "Restarting script..." -ForegroundColor Yellow
                Start-Process powershell -ArgumentList "-NoExit", "-File", "'$($MyInvocation.MyCommand.Path)'"
                exit
            }
        } else {
            Write-Host "Update skipped." -ForegroundColor Cyan
        }
    } else {
        Write-Host "Installing UV..." -ForegroundColor Cyan
        Set-UVLinkMode
        uv pip install uv --link-mode=copy
        Write-Host "UV has been installed." -ForegroundColor Green
        $restartChoice = Read-Host "Do you want to restart the script to apply changes? (Y/N)"
        if ($restartChoice -eq "Y" -or $restartChoice -eq "y") {
            Write-Host "Restarting script..." -ForegroundColor Yellow
            Start-Process powershell -ArgumentList "-NoExit", "-File", "'$($MyInvocation.MyCommand.Path)'"
            exit
        }
    }
}
function Create-VirtualEnvironment {
    Write-Host "Preparing to create virtual environment..." -ForegroundColor Cyan

    # Check and remove old virtual environment
    if (Test-Path $envPath) {
        Write-Host "Found existing virtual environment, removing..." -ForegroundColor Yellow
        try {
            # Ensure no processes are using the virtual environment
            $pythonProcesses = Get-Process python -ErrorAction SilentlyContinue
            if ($pythonProcesses) {
                Write-Host "Stopping Python processes..." -ForegroundColor Yellow
                $pythonProcesses | ForEach-Object { $_.Kill() }
                Start-Sleep -Seconds 2  # Wait for processes to fully terminate
            }
            
            # Delete old virtual environment
            Remove-Item -Path $envPath -Recurse -Force
            Write-Host "Old virtual environment removed successfully." -ForegroundColor Green
        } catch {
            Write-Host "Failed to remove old virtual environment: $_" -ForegroundColor Red
            return
        }
    }

    # Create new virtual environment
    Write-Host "Creating new virtual environment..." -ForegroundColor Cyan
    try {
        python -m venv $envPath
        if (-not $?) { throw "Failed to create virtual environment" }
        Write-Host "Virtual environment created successfully." -ForegroundColor Green
    } catch {
        Write-Host "Failed to create virtual environment: $_" -ForegroundColor Red
        return
    }

    # Activate environment and install packages
    Write-Host "Installing/Updating pip and uv in the new environment..." -ForegroundColor Cyan
    try {
        Wait-ActivateEnvironment
        python -m pip install --upgrade pip
        Set-UVLinkMode
        pip install uv
        if (Get-Command uv -ErrorAction SilentlyContinue) {
            Write-Host "UV installed successfully in $envName." -ForegroundColor Green
            Write-Host "Activate the environment with: $envName\Scripts\activate"
        } else {
            throw "UV installation verification failed"
        }
    } catch {
        Write-Host "Failed to setup virtual environment: $_" -ForegroundColor Red
        return
    }
}

function Install-Packages {
    if (-not ($env:VIRTUAL_ENV)) {
        Wait-ActivateEnvironment
    }
    $packages = Read-Host "Enter package names separated by spaces"
    if ([string]::IsNullOrWhiteSpace($packages)) {
        Write-Host "No packages specified."
        return
    }
    Set-UVLinkMode
    uv pip install $packages --link-mode=copy
    Write-Host "Packages installed successfully."
}

function Install-RequirementsTxt {
    if (-not ($env:VIRTUAL_ENV)) {
        Wait-ActivateEnvironment
    }
    if (Test-Path $requirementsFile) {
        Set-UVLinkMode
        uv pip install -r $requirementsFile --link-mode=copy
        Write-Host "Packages installed successfully."
    } else {
        Write-Host "Error: $requirementsFile not found."
    }
}

function Generate-RequirementsTxt {
    if (-not ($env:VIRTUAL_ENV)) {
        Wait-ActivateEnvironment
    }
    uv pip freeze > $requirementsFile
    Write-Host "$requirementsFile generated successfully."
}

function List-Packages {
    if (-not ($env:VIRTUAL_ENV)) {
        Wait-ActivateEnvironment
    }
    uv pip list
}
function Wait-ActivateEnvironment {
    # Wait for virtual environment activation to complete
    if (-not ($env:VIRTUAL_ENV)) {
        $activateScriptPath = "$envPath\Scripts\activate.ps1"
        if (Test-Path $activateScriptPath) {
            Write-Host "Activating virtual environment using: $activateScriptPath" -ForegroundColor Cyan
            try {
                . $activateScriptPath
                Write-Host "Virtual environment activated." -ForegroundColor Green
            } catch {
                Write-Host "Failed to activate virtual environment using dot-sourcing: $_" -ForegroundColor Red
                throw "Failed to activate virtual environment"
            }
        } else {
            Write-Host "Error: Activation script not found at $activateScriptPath" -ForegroundColor Red
            throw "Activation script not found"
        }
    }
}
function Activate-VirtualEnvironment {
    if (Test-Path $envPath) {
        Write-Host "Starting interactive virtual environment session..." -ForegroundColor Green
        Write-Host "Type 'exit' to leave the virtual environment session" -ForegroundColor Green
        PowerShell -NoExit -Command "& '$envPath\Scripts\activate.ps1'; Set-Location '$PSScriptRoot'"
    } else {
        Write-Host "Error: Virtual environment not found. Please create it first." -ForegroundColor Red
    }
}

function Show-Menu {
    Clear-Host
    Write-Host "================ UV Pip Best Practices Menu ================="
    Write-Host "1: Create($envName)"
    Write-Host "2: Create($envName) && Install requirements.txt"
    Write-Host "3: Activate($envName)"
    Write-Host "4: ($envName)Install packages by user input"
    Write-Host "5: ($envName)Install packages from requirements.txt"
    Write-Host "6: ($envName)Generate requirements.txt"
    Write-Host "7: ($envName)List installed packages"
    Write-Host "8: Install UV globally"
    Write-Host "9: Update pip globally"
    Write-Host "0: Exit"
    Write-Host "==========================================================="
}

# Main menu loop
do {
    Show-Menu
    Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
    $selection = Read-Host "Please select an option"    
    switch ($selection) {
        '1' {
            Create-VirtualEnvironment
        }
        '2' {
            Create-VirtualEnvironment
            Install-RequirementsTxt
        }
        '3' {
            Activate-VirtualEnvironment
        }
        '4' {
            Install-Packages
        }
        '5' {
            Install-RequirementsTxt
        }
        '6' {
            Generate-RequirementsTxt
        }
        '7' {
            List-Packages
        }
        '8' {
            # If in virtual environment, exit first
            if ($env:VIRTUAL_ENV) {
                deactivate
                Write-Host "Exited virtual environment for global installation..." -ForegroundColor Yellow
            }
            powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
        }   
        '9' {
            # If in virtual environment, exit first
            if ($env:VIRTUAL_ENV) {
                deactivate
                Write-Host "Exited virtual environment for global installation..." -ForegroundColor Yellow
            }
            python -m pip install --upgrade pip
        }      
        '0' {
            exit
        }
    }
    Pause
} until ($selection -eq '0')
