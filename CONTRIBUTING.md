# Contributing to NEP_Automation_Toolkit

Thank you for your interest in contributing to this project! This toolkit demonstrates automated grid planning workflows for transmission system operators.

## How to Contribute

### Reporting Issues

If you find a bug or have a suggestion for improvement:

1. Check if the issue already exists in the [Issues](https://github.com/omari91/NEP_Automation_Toolkit/issues) section
2. If not, create a new issue with a clear title and description
3. Include relevant details:
   - Steps to reproduce (for bugs)
   - Expected vs. actual behavior
   - Your environment (Python version, OS, pandapower version)
   - Error messages or logs

### Suggesting Enhancements

We welcome ideas for new features or improvements:

- **Grid modeling enhancements**: Additional components (transformers, shunts, switches)
- **Analysis features**: Voltage stability, short-circuit calculations, optimization
- **Data import/export**: CIM/CGMES support, PSS/E format compatibility
- **Visualization**: Network diagrams, result plots, interactive dashboards
- **Performance**: Parallelization, optimization for large networks

### Submitting Code

1. **Fork the repository** and create a new branch for your feature or fix
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Write clean, documented code**
   - Follow PEP 8 style guidelines
   - Add docstrings to functions and classes
   - Include inline comments for complex logic

3. **Test your changes**
   - Ensure the script runs without errors
   - Verify power flow convergence
   - Test edge cases (e.g., contingencies causing divergence)

4. **Commit with clear messages**
   ```bash
   git commit -m "Add: HVDC contingency analysis for SuedOstLink"
   ```

5. **Push to your fork and submit a Pull Request**
   ```bash
   git push origin feature/your-feature-name
   ```

6. **Pull Request Guidelines**
   - Provide a clear description of the changes
   - Reference any related issues
   - Explain the motivation and impact
   - Include screenshots or results if applicable

## Development Setup

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/NEP_Automation_Toolkit.git
cd NEP_Automation_Toolkit

# Install dependencies
pip install -r requirements.txt

# Run the toolkit
python grid_simulation_toolkit.py
```

## Code Style

- Use meaningful variable names (e.g., `line_loading_percent` not `ll`)
- Keep functions focused and under 50 lines where possible
- Use type hints for function parameters and returns
- Document assumptions (e.g., voltage levels, impedance values)

## Areas for Contribution

### Priority Areas

1. **Real Grid Data Integration**: Import actual 50Hertz network topology
2. **Advanced Contingency Analysis**: N-2, N-1-1 scenarios
3. **Optimization**: Redispatch recommendations, optimal power flow
4. **Renewable Integration**: Wind/solar forecast integration, curtailment analysis
5. **Reporting**: Export results to PDF, Excel, or PowerBI-compatible formats

### Good First Issues

- Add unit tests for grid creation functions
- Improve error messages for convergence failures
- Add command-line arguments for configuration
- Create visualization of grid topology
- Document the mathematical basis for N-1 analysis

## Questions?

Feel free to open an issue with the `question` label, or reach out to discuss potential contributions.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
