"""
Monkey patch to fix hyperactive 4.6.1's broken EnsembleOptimizer import.

This patch must be imported BEFORE basicpy imports hyperactive.
It pre-imports and patches gradient_free_optimizers to add EnsembleOptimizer.
"""
import sys

def apply_patch():
    """Apply the monkey patch to gradient_free_optimizers."""
    # Pre-import gradient_free_optimizers to patch it before hyperactive imports it
    try:
        import gradient_free_optimizers
    except ImportError:
        # If not installed yet, we'll patch it when it gets imported
        # Register a hook to patch it when it's imported
        import importlib
        
        original_import = importlib.import_module
        
        def patched_import(name, package=None):
            module = original_import(name, package)
            if name == 'gradient_free_optimizers':
                _add_ensemble_optimizer(module)
            return module
        
        importlib.import_module = patched_import
        return
    
    # Patch it now if already imported
    _add_ensemble_optimizer(gradient_free_optimizers)

def _add_ensemble_optimizer(gradient_free_optimizers_module):
    """Add EnsembleOptimizer to gradient_free_optimizers module."""
    # Check if EnsembleOptimizer already exists
    if hasattr(gradient_free_optimizers_module, 'EnsembleOptimizer'):
        return
    
    # Create a dummy EnsembleOptimizer class
    class EnsembleOptimizer:
        """Dummy EnsembleOptimizer class for compatibility with hyperactive 4.6.1."""
        
        def __init__(self, *args, **kwargs):
            """Initialize dummy optimizer."""
            pass
        
        def search(self, *args, **kwargs):
            """Dummy search method."""
            raise NotImplementedError(
                "EnsembleOptimizer is not available in this version of gradient_free_optimizers. "
                "This is a compatibility shim for hyperactive 4.6.1. "
                "The BaSiC algorithm should not use this optimizer."
            )
    
    # Add it to the module
    gradient_free_optimizers_module.EnsembleOptimizer = EnsembleOptimizer
    
    # Also add it to __all__ if it exists
    if hasattr(gradient_free_optimizers_module, '__all__'):
        if 'EnsembleOptimizer' not in gradient_free_optimizers_module.__all__:
            gradient_free_optimizers_module.__all__.append('EnsembleOptimizer')

# Apply the patch immediately when this module is imported
apply_patch()
