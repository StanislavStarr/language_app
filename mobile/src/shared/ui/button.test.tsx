import { fireEvent, render, screen } from '@testing-library/react-native';

import { Button } from './button';

describe('Button', () => {
  it('calls onPress when pressed', async () => {
    const onPress = jest.fn();
    await render(<Button label="Сохранить" onPress={onPress} />);

    await fireEvent.press(screen.getByRole('button', { name: 'Сохранить' }));

    expect(onPress).toHaveBeenCalledTimes(1);
  });

  it('does not call onPress when disabled', async () => {
    const onPress = jest.fn();
    await render(<Button label="Сохранить" onPress={onPress} disabled />);

    await fireEvent.press(screen.getByRole('button', { name: 'Сохранить' }));

    expect(onPress).not.toHaveBeenCalled();
  });

  it('does not call onPress while loading', async () => {
    const onPress = jest.fn();
    await render(<Button label="Сохранить" onPress={onPress} loading />);

    await fireEvent.press(screen.getByRole('button', { name: 'Сохранить' }));

    expect(onPress).not.toHaveBeenCalled();
  });

  it('shows a busy indicator instead of the label while loading', async () => {
    await render(<Button label="Сохранить" onPress={jest.fn()} loading />);

    expect(screen.getByRole('button', { name: 'Сохранить' })).toBeBusy();
    expect(screen.queryByText('Сохранить')).not.toBeOnTheScreen();
  });
});
