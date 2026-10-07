// Hand-written mirrors of the serializer shapes (SPEC section 8, DESIGN 1.3). Money is a string.

export interface Me {
  id: number;
  email: string;
}

export interface TokenPair {
  access: string;
  refresh: string;
}

export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}
