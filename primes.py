def primes(limit):
    return [n for n in range(2, limit + 1) if all(n % d for d in range(2, int(n ** 0.5) + 1))]

if __name__ == '__main__':
    print(primes(30))
