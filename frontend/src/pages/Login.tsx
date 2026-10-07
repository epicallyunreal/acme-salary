import type { FormEvent } from 'react';

// Placeholder for step 1: the fields and the button exist, nothing is submitted yet.
// Step 3 wires it to /api/v1/auth/login/ and styles it with the theme.
export function Login() {
  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
  };

  return (
    <main>
      <h1>ACME Salary</h1>
      <p>Sign in to manage compensation</p>
      <form onSubmit={onSubmit} aria-label="Sign in">
        <div>
          <label htmlFor="email">Email</label>
          <input id="email" name="email" type="email" autoComplete="username" />
        </div>
        <div>
          <label htmlFor="password">Password</label>
          <input id="password" name="password" type="password" autoComplete="current-password" />
        </div>
        <button type="submit">Sign in</button>
      </form>
    </main>
  );
}
