import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import norm

# ======================
# 1. Espectro P(IS) 1D (pico claro)
# ======================
is_shift = np.linspace(-0.5, 0.5, 1000)
spectrum_is = norm.pdf(is_shift, loc=0, scale=0.1)  # Pequeño desvío (pico muy nitido)

# ======================
# 2. Espectro P(IS, ΔEQ) 2D (con componentes nitidos)
# ======================
delta_eq = np.linspace(-0.3, 0.3, 300)
is_val = np.linspace(-0.3, 0.3, 300)
X, Y = np.meshgrid(delta_eq, is_val)
# Componente principal (nitido)
spectrum_is_delta = np.exp(-((X - 0.1)**2 + (Y - 0.1)**2) / (0.05**2))
# Componente secundaria (ligeramente más ancha)
spectrum_is_delta_noise = spectrum_is_delta * 0.8 + 0.05 * np.random.normal(size=X.shape)

# ======================
# 3. Espectro P(BHF, IS) 2D (con pico triple)
# ======================
bhf_val = np.linspace(-0.2, 0.2, 250)
is_comp = np.linspace(-0.2, 0.2, 250)
X_bhf, Y_bhf = np.meshgrid(bhf_val, is_comp)
# Tres componentes con diferentes nitiduras
spectrum_bhf = (
    0.4 * np.exp(-((X_bhf - 0.05)**2 + (Y_bhf - 0.05)**2) / (0.05**2)) 
    + 0.3 * np.exp(-((X_bhf - 0.15)**2 + (Y_bhf - 0.15)**2) / (0.04**2))
    + 0.2 * np.exp(-((X_bhf - 0.25)**2 + (Y_bhf - 0.25)**2) / (0.05**2))
)

# ======================
# Genera imágenes
# ======================
plt.figure(figsize=(12, 8))

# Gráfico 1D
plt.subplot(1, 3, 1)
plt.plot(is_shift, spectrum_is, 'r-')
plt.title('P(IS) 1D (pico muy nitido)', fontsize=12)
plt.xlabel('IS (m/s)', fontsize=10)
plt.ylabel('Intensidad', fontsize=10)
plt.grid(True, alpha=0.3)

# Gráfico 2D P(IS, ΔEQ)
plt.subplot(1, 3, 2)
plt.imshow(
    spectrum_is_delta,
    extent=[-0.3, 0.3, -0.3, 0.3],
    aspect='auto',
    cmap='viridis',
    alpha=0.8
)
plt.title('P(IS, ΔEQ) 2D (componente principal)', fontsize=12)
plt.xlabel('Delta_eq (m/s)', fontsize=10)
plt.ylabel('IS (m/s)', fontsize=10)
plt.grid(True, alpha=0.1)

# Gráfico 2D P(BHF, IS)
plt.subplot(1, 3, 3)
plt.imshow(
    spectrum_bhf,
    extent=[-0.2, 0.2, -0.2, 0.2],
    aspect='auto',
    cmap='plasma',
    alpha=0.8,
    vmin=0,
    vmax=0.4
)
plt.title('P(BHF, IS) 2D (pico triple)', fontsize=12)
plt.xlabel('BHF (m/s)', fontsize=10)
plt.ylabel('IS (m/s)', fontsize=10)
plt.grid(True, alpha=0.1)

plt.tight_layout()
plt.savefig('data_sample/spectra.png')
plt.show()