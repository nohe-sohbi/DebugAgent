import { render, screen } from '@testing-library/react';
import App from './App';

test('renders project analysis heading', () => {
  render(<App />);
  const linkElement = screen.getByText(/Project Analysis/i);
  expect(linkElement).toBeInTheDocument();
});
