import sys
import binascii
import json
import importlib
import pkgutil
import os
import time

# --- CONFIGURAÇÃO INICIAL ---
try:
    with open("vetores_nist.json", "r") as f:
        TEST_VECTORS = json.load(f)
except Exception:
    print(json.dumps({"error": "Falha ao ler vetores_nist.json", "status": "SETUP_ERROR"}))
    sys.exit(1)

TARGET_LIB_ARG = sys.argv[1] if len(sys.argv) > 1 else None

# Mapeamentos de Nomes (PyPI -> Import Python)
KNOWN_MAPPINGS = {
    "pycrypto": "Crypto",
    "pycryptodome": "Crypto",
    "pycryptodomex": "Cryptodome",
    "python-aescipher": "aescipher",
    "aes-python": "aes",
    "pure-python-aes": "aes",
    "pyaes": "pyaes",
    "tlslite-ng": "tlslite",
    "tlslite": "tlslite",
    "oscrypto": "oscrypto",
    "py3rijndael": "py3rijndael",
    "aes": "aes",
    "cryptography": "cryptography",
    "phoenixaes": "phoenixAES"
}

# Locais Específicos (Sniper Mode)
KNOWN_LOCATIONS = {
    "tlslite": ["tlslite.utils.aes", "tlslite.utils.rijndael"],
    "tlslite-ng": ["tlslite.utils.aes", "tlslite.utils.rijndael"],
    "pyaes": ["pyaes"],  # Aponta para o pacote raiz onde as classes estão expostas
    "cryptography": ["cryptography.hazmat.primitives.ciphers"]
}


# --- ADAPTERS (Classes para corrigir libs fora do padrão) ---

class PyaesAdapter:
    """Adaptador para a lib 'pyaes' que usa classes distintas por modo"""

    def __init__(self, key, mode, iv=None):
        import pyaes
        # Seleciona a classe correta baseada no modo
        if mode == 1:  # ECB
            self.cipher = pyaes.AESModeOfOperationECB(key)
        elif mode == 2:  # CBC
            if iv is None: iv = b'\0' * 16
            self.cipher = pyaes.AESModeOfOperationCBC(key, iv=iv)
        elif mode == 3:  # CFB
            if iv is None: iv = b'\0' * 16
            self.cipher = pyaes.AESModeOfOperationCFB(key, iv=iv, segment_size=16)
        else:
            raise ValueError(f"Modo {mode} não suportado pelo adaptador Pyaes")

    def encrypt(self, data):
        return self.cipher.encrypt(data)

    def decrypt(self, data):
        return self.cipher.decrypt(data)


class Py3RijndaelAdapter:
    """Adaptador para py3rijndael (exige block_size no init)"""

    def __init__(self, key, mode, iv=None):
        from py3rijndael import Rijndael
        self.rijndael = Rijndael(key, block_size=16)
        self.mode = mode
        self.iv = iv

    def encrypt(self, data):
        return self.rijndael.encrypt(data)

    def decrypt(self, data):
        return self.rijndael.decrypt(data)


class OscryptoAdapter:
    """Adaptador para oscrypto (API funcional, não O.O.)"""

    def __init__(self, key, mode, iv=None):
        self.key = key
        self.iv = iv or (b'\x00' * 16)
        self.mode_str = 'ecb'
        if mode == 2: self.mode_str = 'cbc'

    def encrypt(self, data):
        from oscrypto.symmetric import aes_cbc_encrypt, aes_ecb_encrypt
        if self.mode_str == 'cbc':
            ct, _ = aes_cbc_encrypt(self.key, data, self.iv)
            return ct
        return aes_ecb_encrypt(self.key, data)

    def decrypt(self, data):
        from oscrypto.symmetric import aes_cbc_decrypt, aes_ecb_decrypt
        if self.mode_str == 'cbc':
            return aes_cbc_decrypt(self.key, data, self.iv)
        return aes_ecb_decrypt(self.key, data)


class AesPackageAdapter:
    """Adaptador para o pacote 'aes' (inteiros/listas)"""

    def __init__(self, key, mode, iv=None):
        from aes import aes
        self.key_int = int.from_bytes(key, byteorder='big')
        self.key_len = len(key) * 8
        self.cipher = aes.aes(self.key_int, self.key_len)
        self.mode = mode

    def encrypt(self, data):
        val = int.from_bytes(data, byteorder='big')
        ct_list = self.cipher.enc_once(val)
        if isinstance(ct_list, int): return ct_list.to_bytes(16, byteorder='big')
        from aes.utils import arr8bit2int
        return arr8bit2int(ct_list).to_bytes(16, byteorder='big')

    def decrypt(self, data):
        val = int.from_bytes(data, byteorder='big')
        pt_list = self.cipher.dec_once(val)
        if isinstance(pt_list, int): return pt_list.to_bytes(16, byteorder='big')
        from aes.utils import arr8bit2int
        return arr8bit2int(pt_list).to_bytes(16, byteorder='big')


# ------------------------------------------------------------

def get_special_adapter(lib_name, key, mode, iv):
    """Fábrica de Adaptadores"""
    lib_lower = lib_name.lower()

    if "pyaes" in lib_lower:  # NOVO: Suporte explícito para pyaes
        return PyaesAdapter(key, mode, iv)

    if "py3rijndael" in lib_lower:
        return Py3RijndaelAdapter(key, mode, iv)

    if "oscrypto" in lib_lower:
        if mode not in [1, 2]: return None
        return OscryptoAdapter(key, mode, iv)

    if lib_lower == "aes":
        if mode != 1: return None
        return AesPackageAdapter(key, mode, iv)

    return None


def find_aes_class_in_module(module, depth=0):
    if depth > 3: return None
    if hasattr(module, "AES"): return module.AES
    if hasattr(module, "Aes"): return module.Aes

    mod_name = module.__name__.lower()
    if hasattr(module, "new") and ("aes" in mod_name or "rijndael" in mod_name or "crypto" in mod_name):
        return module

    if hasattr(module, "__path__"):
        try:
            for _, name, _ in pkgutil.iter_modules(module.__path__):
                name_lower = name.lower()
                if any(x in name_lower for x in
                       ["cipher", "aes", "algo", "crypto", "block", "mode", "rijndael", "utils"]):
                    try:
                        full_name = f"{module.__name__}.{name}"
                        sub_mod = sys.modules.get(full_name) or importlib.import_module(full_name)
                        found = find_aes_class_in_module(sub_mod, depth + 1)
                        if found: return found
                    except:
                        continue
        except:
            pass
    return None


def measure_performance(cipher_factory_lambda, pt_bin):
    try:
        cipher = cipher_factory_lambda()
        if not hasattr(cipher, 'encrypt'): return 0, 0
        cipher.encrypt(pt_bin)

        iters = 500
        t1 = time.perf_counter()
        for _ in range(iters):
            c = cipher_factory_lambda()
            c.encrypt(pt_bin)
        t2 = time.perf_counter()
        avg_enc = ((t2 - t1) / iters) * 1000

        temp_c = cipher_factory_lambda()
        ct = temp_c.encrypt(pt_bin)

        t3 = time.perf_counter()
        for _ in range(iters):
            c = cipher_factory_lambda()
            c.decrypt(ct)
        t4 = time.perf_counter()
        avg_dec = ((t4 - t3) / iters) * 1000

        return avg_enc, avg_dec
    except:
        return 0, 0


def teste_generico(aes_impl, test_case, lib_name):
    try:
        key = binascii.unhexlify(test_case["chave_hex"])
        pt = binascii.unhexlify(test_case["texto_plano_hex"])
        iv = binascii.unhexlify(test_case["iv_hex"]) if test_case["iv_hex"] else None
        expected = test_case["texto_cifrado_esperado"]

        mode_val = 1  # ECB
        if test_case["modo"] == "CBC":
            mode_val = 2
        elif test_case["modo"] == "CFB":
            mode_val = 3

        if aes_impl and not isinstance(aes_impl, str) and hasattr(aes_impl, "MODE_CBC"):
            if test_case["modo"] == "CBC":
                mode_val = getattr(aes_impl, "MODE_CBC")
            elif test_case["modo"] == "CFB":
                mode_val = getattr(aes_impl, "MODE_CFB")

        factory_lambda = None
        cipher = None

        # 1. Tenta Adapter (Prioridade para pyaes, oscrypto, etc)
        adapter_instance = get_special_adapter(lib_name, key, mode_val, iv)
        if adapter_instance:
            cipher = adapter_instance
            factory_lambda = lambda: get_special_adapter(lib_name, key, mode_val, iv)

        # 2. Tenta Genérico
        if not cipher and aes_impl:
            factory = aes_impl.new if hasattr(aes_impl, "new") else aes_impl
            try:
                args = [key, mode_val]
                if test_case["modo"] != "ECB" and iv: args.append(iv)
                cipher = factory(*args)
                factory_lambda = lambda: factory(*args)
            except:
                try:
                    kwargs = {'key': key, 'mode': mode_val}
                    if test_case["modo"] != "ECB": kwargs['iv'] = iv
                    cipher = factory(**kwargs)
                    factory_lambda = lambda: factory(**kwargs)
                except:
                    pass

        if not cipher: return False, "Instanciação falhou", None

        ct = cipher.encrypt(pt)
        if isinstance(ct, str): ct = ct.encode('latin-1')
        ct_hex = binascii.hexlify(ct).decode().upper()

        if ct_hex == expected: return True, "PASS", factory_lambda
        return False, f"DIVERGÊNCIA: {ct_hex}", None

    except Exception as e:
        return False, f"CRASH: {str(e)}", None


def run_tests():
    if not TARGET_LIB_ARG: sys.exit(1)

    raw = TARGET_LIB_ARG
    candidates = []
    if raw.lower() in KNOWN_MAPPINGS: candidates.append(KNOWN_MAPPINGS[raw.lower()])
    candidates.append(raw.lower().replace('-', '_'))
    candidates.append(raw)

    aes_impl = None

    # Lista de libs que usam Adapter e não precisam de busca de classe
    special_libs = ["oscrypto", "py3rijndael", "aes", "pyaes"]
    is_special = any(x in raw.lower() for x in special_libs)
    if raw.lower() == "aes": is_special = True

    if not is_special:
        if raw in KNOWN_LOCATIONS:
            for loc in KNOWN_LOCATIONS[raw]:
                try:
                    mod = importlib.import_module(loc)
                    aes_impl = find_aes_class_in_module(mod)
                    if aes_impl: break
                except:
                    pass

        if not aes_impl:
            for cand in candidates:
                try:
                    mod = importlib.import_module(cand)
                    aes_impl = find_aes_class_in_module(mod)
                    if aes_impl: break
                except:
                    continue

    if not aes_impl and not is_special:
        print(json.dumps({"error": "Implementation not found", "status": "NOT_FOUND"}))
        sys.exit(1)

    results = {}
    passou_algo = False
    perf_factory = None

    for tc in TEST_VECTORS:
        ok, msg, factory = teste_generico(aes_impl, tc, raw)
        results[tc["id_teste"]] = "PASS" if ok else "FAIL"
        if ok:
            passou_algo = True
            perf_factory = factory

    t_enc, t_dec = 0, 0
    if passou_algo and perf_factory and len(TEST_VECTORS) > 0:
        k = binascii.unhexlify(TEST_VECTORS[0]["chave_hex"])
        pt = binascii.unhexlify(TEST_VECTORS[0]["texto_plano_hex"])
        t_enc, t_dec = measure_performance(perf_factory, pt)

    results["enc_time"] = t_enc
    results["dec_time"] = t_dec
    print(json.dumps(results))


if __name__ == "__main__":
    run_tests()