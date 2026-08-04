echo "Install dependencies..."
pip install -r requirements.txt     # PyYAML >= 6.0
echo "Installation dependencies done."
echo "Install entry point..."
pip install -e .                   # Install entry point → command `agra` langsung tersedia di PATH
echo "Installation entry point done."