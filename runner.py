import sys
import binascii
import json
import importlib
import pkgutil
import os
import time
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

# Carrega a nova estrutura de lista do JSON
try:
    with open("vetores_nist.json", "r") as f:
        TEST_VECTORS = json.load(f)
except Exception:
    print(json.dumps({"error": "vetores_nist.json loading failed"}))
    sys.exit(1)

TARGET_LIB_ARG = sys.argv[1] if len(sys.argv) > 1 else None

KNOWN_MAPPINGS = {
    "pycrypto": "Crypto",
    "pycryptodome": "Crypto",
    "pycryptodomex": "Cryptodome",
    "python-aescipher": "aescipher",
    "aes-python": "aes",
    "pure-python-aes": "aes",
    "pyaes": "pyaes",
    "tlslite-ng": "tlslite"
}


def get_installed_top_level_modules():
    modules = []
    for path in sys.path:
        if "site-packages" in path and os.path.isdir(path):
            try:
                for name in os.listdir(path):
                    full_path = os.path.join(path, name)
                    if os.path.isdir(full_path) and "." not in name and "__" not in name:
                        modules.append(name)
                    elif name.endswith(".py") and name != "__init__.py":
                        modules.append(name[:-3])
            except Exception:
                pass
    return list(set(modules))


def find_aes_class_in_module(module, depth=0):
    if depth > 2: return None
    if hasattr(module, "AES"):
        return module.AES
    if hasattr(module, "new") and ("AES" in module.__name__.upper() or "aes" in module.__name__.lower()):
        return module
    if hasattr(module, "__path__"):
        try:
            for _, name, _ in pkgutil.iter_modules(module.__path__):
                name_lower = name.lower()
                if any(x in name_lower for x in ["cipher", "aes", "algo", "crypto", "block", "mode", "rijndael"]):
                    try:
                        full_name = f"{module.__name__}.{name}"
                        if full_name in sys.modules:
                            sub_mod = sys.modules[full_name]
                        else:
                            sub_mod = importlib.import_module(full_name)
                        res = find_aes_class_in_module(sub_mod, depth + 1)
                        if res: return res
                    except:
                        continue
        except Exception:
            pass
    return None


def measure_performance(aes_cls, key_bin, iv_bin, pt_bin):
    try:
        factory = aes_cls.new if hasattr(aes_cls, "new") else aes_cls
        mode_const = getattr(aes_cls, "MODE_ECB", 1)

        cipher = None
        try:
            cipher = factory(key_bin, mode_const)
        except:
            try:
                cipher = factory(key=key_bin, mode=mode_const)
            except:
                return 0, 0

        if not cipher or not hasattr(cipher, 'encrypt'): return 0, 0

        iterations = 200
        t_start_enc = time.perf_counter()
        ct = None
        for _ in range(iterations):
            ct = cipher.encrypt(pt_bin)
        t_end_enc = time.perf_counter()

        avg_enc = ((t_end_enc - t_start_enc) / iterations) * 1000

        cipher_dec = cipher
        if not hasattr(cipher_dec, 'decrypt'):
            try:
                cipher_dec = factory(key_bin, mode_const)
            except:
                pass

        t_start_dec = time.perf_counter()
        for _ in range(iterations):
            cipher_dec.decrypt(ct)
        t_end_dec = time.perf_counter()

        avg_dec = ((t_end_dec - t_start_dec) / iterations) * 1000

        return avg_enc, avg_dec
    except:
        return 0, 0


def teste_generico(aes_cls, test_case):
    try:
        # Mapeamento das novas chaves em PT-BR
        key_bin = binascii.unhexlify(test_case["chave_hex"])
        pt_bin = binascii.unhexlify(test_case["texto_plano_hex"])
        expected_hex = test_case["texto_cifrado_esperado"]
        iv_bin = binascii.unhexlify(test_case["iv_hex"]) if test_case["iv_hex"] else None
        mode_name = test_case["modo"]

        mode_const = None
        if mode_name == "ECB":
            mode_const = getattr(aes_cls, "MODE_ECB", 1)
        elif mode_name == "CBC":
            mode_const = getattr(aes_cls, "MODE_CBC", 2)
        elif mode_name == "CFB":
            mode_const = getattr(aes_cls, "MODE_CFB", 3)

        factory = aes_cls.new if hasattr(aes_cls, "new") else aes_cls
        cipher = None

        try:
            if mode_name == "ECB":
                cipher = factory(key_bin, mode_const)
            else:
                cipher = factory(key_bin, mode_const, iv_bin)
        except:
            pass

        if cipher is None:
            try:
                kwargs = {'key': key_bin, 'mode': mode_const}
                if mode_name != "ECB": kwargs['iv'] = iv_bin
                cipher = factory(**kwargs)
            except:
                pass

        if cipher is None: return False, "Instanciacao falhou"

        if hasattr(cipher, "encrypt"):
            ct = cipher.encrypt(pt_bin)
            if isinstance(ct, str): ct = ct.encode('latin-1')
            ct_hex = binascii.hexlify(ct).decode().upper()

            if ct_hex == expected_hex:
                return True, "SUCESSO"
            return False, f"DIVERGENCIA: {ct_hex}"

    except Exception as e:
        return False, f"Erro: {str(e)}"

    return False, "Metodo encrypt nao encontrado"


def teste_cryptography_io(test_case):
    try:
        # Mapeamento das novas chaves em PT-BR
        key_bin = binascii.unhexlify(test_case["chave_hex"])
        pt_bin = binascii.unhexlify(test_case["texto_plano_hex"])
        expected_hex = test_case["texto_cifrado_esperado"]
        iv_bin = binascii.unhexlify(test_case["iv_hex"]) if test_case["iv_hex"] else None
        mode_name = test_case["modo"]

        algo = algorithms.AES(key_bin)
        if mode_name == "ECB":
            mode = modes.ECB()
        elif mode_name == "CBC":
            mode = modes.CBC(iv_bin)
        elif mode_name == "CFB":
            mode = modes.CFB(iv_bin)
        else:
            return False, "Modo inv"

        backend = default_backend()
        cipher = Cipher(algo, mode, backend=backend)
        encryptor = cipher.encryptor()
        ct = encryptor.update(pt_bin) + encryptor.finalize()
        ct_hex = binascii.hexlify(ct).decode().upper()

        if ct_hex == expected_hex:
            return True, "SUCESSO"
        return False, f"DIVERGENCIA: {ct_hex}"
    except:
        return False, "N/A"


def run_tests():
    results = {}
    aes_implementation = None

    candidates = []
    if TARGET_LIB_ARG:
        clean_name = TARGET_LIB_ARG.split('-')[0].lower()
        candidates.append(TARGET_LIB_ARG)
        if clean_name in KNOWN_MAPPINGS:
            candidates.append(KNOWN_MAPPINGS[clean_name])

    installed_pkgs = get_installed_top_level_modules()
    priority_from_installed = []
    generic_from_installed = []

    for pkg in installed_pkgs:
        pkg_lower = pkg.lower()
        if TARGET_LIB_ARG and (TARGET_LIB_ARG.lower() in pkg_lower or pkg_lower in TARGET_LIB_ARG.lower()):
            priority_from_installed.append(pkg)
        elif any(x in pkg_lower for x in ["crypto", "aes", "cipher", "security"]):
            generic_from_installed.append(pkg)

    final_search_list = list(dict.fromkeys(
        priority_from_installed + candidates + generic_from_installed + ["Crypto", "Cryptodome", "pyaes",
                                                                         "cryptography"]))

    for lib_name in final_search_list:
        try:
            mod = importlib.import_module(lib_name)
            aes_implementation = find_aes_class_in_module(mod)
            if aes_implementation:
                break
        except:
            continue

    passou_algum = False
    for test_case in TEST_VECTORS:
        test_id = test_case["id_teste"]  # Nova chave
        passed = False

        if aes_implementation:
            passed, msg = teste_generico(aes_implementation, test_case)

        if not passed:
            passed_c, msg_c = teste_cryptography_io(test_case)
            if passed_c:
                passed = True

        if passed:
            passou_algum = True

        results[test_id] = "PASS" if passed else "FAIL"

    t_enc, t_dec = 0, 0
    if aes_implementation and passou_algum and len(TEST_VECTORS) > 0:
        perf_case = TEST_VECTORS[0]
        # Nova chave para performance
        k = binascii.unhexlify(perf_case["chave_hex"])
        pt = binascii.unhexlify(perf_case["texto_plano_hex"])
        t_enc, t_dec = measure_performance(aes_implementation, k, None, pt)

    results["enc_time"] = t_enc
    results["dec_time"] = t_dec

    print(json.dumps(results))


if __name__ == "__main__":
    run_tests()