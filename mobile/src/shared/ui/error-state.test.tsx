import { fireEvent, render, screen } from '@testing-library/react-native';

import { ErrorState } from './error-state';

describe('ErrorState', () => {
  it('shows the message and retries on demand', async () => {
    const onRetry = jest.fn();
    await render(<ErrorState message="Не удалось загрузить" onRetry={onRetry} />);

    expect(screen.getByText('Не удалось загрузить')).toBeOnTheScreen();
    await fireEvent.press(screen.getByRole('button', { name: 'Повторить' }));

    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('hides the retry button without a handler', async () => {
    await render(<ErrorState message="Не удалось загрузить" />);

    expect(screen.queryByRole('button')).not.toBeOnTheScreen();
  });
});
