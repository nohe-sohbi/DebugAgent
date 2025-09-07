import { render, screen } from '@testing-library/react';
import App from './App';

// Mock react-i18next
jest.mock('react-i18next', () => ({
  useTranslation: () => {
    return {
      t: (str) => str,
      i18n: {
        changeLanguage: () => new Promise(() => {}),
      },
    };
  },
}));

test('renders project analysis heading', () => {
  render(<App />);
  const linkElement = screen.getByText(/projectAnalysis/i);
  expect(linkElement).toBeInTheDocument();
});
