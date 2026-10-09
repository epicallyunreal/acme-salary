import { zodResolver } from '@hookform/resolvers/zod';
import { Alert, Box, Button, Paper, TextField, Typography } from '@mui/material';
import { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { Navigate, useNavigate, useSearchParams } from 'react-router';
import { z } from 'zod';

import { useLogin } from '../api/auth';
import { ApiError } from '../api/client';
import { useAccessToken } from '../lib/auth';
import { Credit } from '../components/layout/Credit';
import { safeNext } from '../lib/navigation';

const loginSchema = z.object({
  email: z.email('Enter your email address'),
  password: z.string().min(1, 'Enter your password'),
});

type LoginValues = z.infer<typeof loginSchema>;

function loginMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return 'Email or password is wrong.';
    if (error.status === 429) return 'Too many attempts. Wait a minute and try again.';
  }
  return 'Could not sign in. Check your connection and try again.';
}

export function Login() {
  const token = useAccessToken();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const signIn = useLogin();
  const { register, handleSubmit, formState } = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    mode: 'onBlur',
    defaultValues: { email: '', password: '' },
  });
  // The login has no PageHeader to name the tab, and a sign-out would leave the last page's name.
  useEffect(() => {
    document.title = 'Sign in · ACME Salary';
  }, []);

  if (token !== null) return <Navigate to={safeNext(params.get('next'))} replace />;

  const onSubmit = (values: LoginValues) => {
    signIn.mutate(values, {
      onSuccess: () => navigate(safeNext(params.get('next')), { replace: true }),
    });
  };

  const { ref: emailRef, ...emailField } = register('email');
  const { ref: passwordRef, ...passwordField } = register('password');

  return (
    <Box component="main" sx={{ minHeight: '100dvh', display: 'grid', placeItems: 'center', p: 4 }}>
      {/* The card and the credit are one centred column, so the page's grid has one child to
          centre and does not share its height between them (D80). */}
      <Box
        sx={{
          width: '100%',
          maxWidth: 400,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 3,
        }}
      >
        <Paper sx={{ width: '100%', p: 8 }}>
          <Typography variant="h1" component="h1">
            ACME Salary
          </Typography>
          <Typography color="text.secondary" sx={{ mt: 1, mb: 6 }}>
            Sign in to manage compensation
          </Typography>
          <Box
            component="form"
            noValidate
            aria-label="Sign in"
            onSubmit={handleSubmit(onSubmit)}
            sx={{ display: 'grid', gap: 4 }}
          >
            <TextField
              label="Email"
              type="email"
              autoComplete="username"
              autoFocus
              inputRef={emailRef}
              error={formState.errors.email !== undefined}
              helperText={formState.errors.email?.message}
              {...emailField}
            />
            <TextField
              label="Password"
              type="password"
              autoComplete="current-password"
              inputRef={passwordRef}
              error={formState.errors.password !== undefined}
              helperText={formState.errors.password?.message}
              {...passwordField}
            />
            <Button type="submit" variant="contained" size="large" loading={signIn.isPending}>
              Sign in
            </Button>
            {signIn.isError ? (
              <Alert severity="error" variant="outlined" role="alert">
                {loginMessage(signIn.error)}
              </Alert>
            ) : null}
          </Box>
        </Paper>
        <Credit />
      </Box>
    </Box>
  );
}
